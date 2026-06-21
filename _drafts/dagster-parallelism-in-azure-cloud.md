---
layout: post
title: "Dagster Parallelism in Azure Cloud"
date: 2026-03-21
description: "Fan-out/fan-in with @graph_asset works in-process — until you scale to K8s and need shared storage for manifests and batch metadata. Here is how to wire ADLS IO managers and avoid the Snowflake dict trap on Dagster 1.12."
tags:
  - dagster
  - python
  - data-engineering
  - parallelization
  - azure
image: "/assets/images/posts/dagster-parallelism-in-azure-cloud/cb55bb0aaa.jpg"
---

![](/assets/images/posts/dagster-parallelism-in-azure-cloud/cb55bb0aaa.jpg)

Photo by [NASA](https://unsplash.com/@nasa) on [Unsplash](https://unsplash.com)

### Dagster parallelism in Azure Cloud

In [Parallelizing Your Workflows with Dagster](/2024/09/20/parallelizing-your-workflows-with-dagster.html) I showed a fan-out/fan-in pipeline: split data with `DynamicOut`, process batches with `.map()`, collect with `.collect()`, and wrap it in `@graph_asset`. That example runs in one process and keeps intermediate values in memory (DuckDB + local Dagster storage).

That pattern breaks down when you move heavy work to **Kubernetes Jobs** on separate nodes. Dagster still orchestrates one parent run, but **every step output that must survive until the next step needs a shared store**. In our Azure setup that store is **ADLS Gen2** (Azure Blob), not the warehouse IO manager used for pandas tables.

This post is the sequel: same dynamic graph idea, but with **explicit IO managers** so orchestration handoffs do not fall through to the default Snowflake pandas manager.

### What we are building

The production shape looks like this:

1. **Asset A** — cheap prep work; writes a small **manifest** (`dict`) to blob storage.
2. **Asset B** — reads the manifest from blob, does a one-time side effect (e.g. truncate a staging table in Snowflake), then **fans out** N mapped steps.
3. **Mapped steps** — each launches a K8s Job; returns a small **result dict** (status, job name, counts).
4. **Collector op** — merges mapped results into a summary dict; parent run finishes when all batches complete.

Snowflake is still used **inside** ops for SQL. It is **not** the bus for passing Python objects between Dagster steps.

![Orchestration flow: ADLS pickle handoffs between assets and inner ops; Snowflake only for SQL inside ops](/assets/images/posts/dagster-parallelism-in-azure-cloud/pipeline-flow.svg)

*Orchestration flow (by author). Edit `pipeline-flow.mmd` in the same folder and run `make diagram-dagster-azure-io` to regenerate the SVG.*

### Rule number one: two kinds of persistence

| Kind | Examples | IO manager |
|------|----------|------------|
| **Orchestration handoffs** | manifests, batch specs, run summaries, `dict` / `list` | ADLS pickle (`ADLS2PickleIOManager`) |
| **Analytical tables** | `pd.DataFrame` assets, dbt outputs | Snowflake pandas IO (default in our repo) |

If you return a **`dict`** from an op and do not set an IO manager, Dagster uses the **default** resource — in our monorepo that is **`SnowflakeIOManager`**, which only accepts **`DataFrame`**. The op body can succeed and the step still fails on **handle output**.

Typical error:

```
SnowflakeIOManager does not have a handler for type '<class 'dict'>'
```

The logs are misleading: you often see the business logic succeed (`Truncated 0 rows`, `Queued batch …`) and then the run dies while **persisting the return value**.

### Register a dedicated ADLS IO manager

We use `dagster-azure` and a separate prefix per pipeline so blobs do not collide:

```python
from dagster_azure.adls2 import (
    ADLS2DefaultAzureCredential,
    ADLS2PickleIOManager,
    ADLS2Resource,
)

adls2 = ADLS2Resource(
    storage_account="yourstorageaccount",
    credential=ADLS2DefaultAzureCredential(
        kwargs={"exclude_environment_credential": True}
    ),
)

io_manager_my_pipeline = ADLS2PickleIOManager(
    adls2_file_system="dagster-iomanagers",
    adls2_prefix="my-pipeline",
    adls2=adls2,
)
```

Expose it in `Definitions`:

```python
defs = Definitions(
    assets=[...],
    resources={
        "io_manager": snowflake_pandas_io_manager,  # default for DataFrame assets
        "io_manager_my_pipeline": io_manager_my_pipeline,
    },
)
```

Use a **constant** for the resource key so assets and ops stay in sync:

```python
IO_MANAGER_MY_PIPELINE = "io_manager_my_pipeline"
```

### Pin ADLS on every asset and op that moves non-DataFrame data

**Upstream assets** — decorator level works on `@asset`:

```python
@asset(
    partitions_def=schema_partitions,
    io_manager_key=IO_MANAGER_MY_PIPELINE,
)
def batch_manifest(context) -> dict:
    manifest = build_manifest(...)
    return manifest
```

**Loading that asset inside a graph** — tell Dagster which manager to use for the input (not the default Snowflake loader):

```python
@graph_asset(
    ins={
        "batch_manifest": AssetIn(
            key=AssetKey("batch_manifest"),
            input_manager_key=IO_MANAGER_MY_PIPELINE,
        ),
    },
)
def run_batches(batch_manifest: dict):
    ...
```

**Inner ops** — pin IO on **`Out`**, especially when the return type is not a `DataFrame`:

```python
@op(out=Out(io_manager_key=IO_MANAGER_MY_PIPELINE))
def prepare(batch_manifest: dict) -> dict:
    do_side_effect_in_snowflake(...)
    return batch_manifest


@op(out=DynamicOut(dict, io_manager_key=IO_MANAGER_MY_PIPELINE))
def fan_out(context, batch_manifest: dict):
    for batch_key, payload in batches(batch_manifest):
        yield DynamicOutput(payload, mapping_key=sanitize(batch_key))


@op(out=Out(io_manager_key=IO_MANAGER_MY_PIPELINE))
def run_one_batch(context, batch: dict) -> dict:
    launch_k8s_job(...)
    return {"batch_key": batch["batch_key"], "status": "completed"}


@op(out=Out(io_manager_key=IO_MANAGER_MY_PIPELINE))
def summarize(context, results: list[dict]) -> dict:
    summary = {"batch_count": len(results), "results": results}
    context.add_output_metadata({"batch_count": len(results)})
    return summary
```

**Graph wiring** — same as the 2024 post:

```python
@graph_asset(
    group_name="my_pipeline",
    partitions_def=schema_partitions,
    ins={
        "batch_manifest": AssetIn(
            key=AssetKey("batch_manifest"),
            input_manager_key=IO_MANAGER_MY_PIPELINE,
        ),
    },
)
def orchestrate(batch_manifest: dict) -> dict:
    prepared = prepare(batch_manifest)
    mapped = fan_out(prepared).map(run_one_batch)
    return summarize(mapped.collect())
```

Every op that returns a `dict` in this chain declares `io_manager_key=IO_MANAGER_MY_PIPELINE`. The **final** op (`summarize`) is the graph return value — on Dagster 1.12 its `Out` is what actually controls where the asset output is stored (see gotchas below).

### Dagster 1.12 gotchas (read this before debugging for a week)

We hit several APIs that **look** supported in docs or newer versions but **fail at import time or runtime** on **1.12.x**:

| Approach | On our 1.12 deploy |
|----------|-------------------|
| `@graph_asset(io_manager_key=…)` | Not supported on the decorator |
| `asset.with_attributes(io_manager_key=…)` | `TypeError` at **import** — code location never loads |
| `@graph_multi_asset(description=…)` | `TypeError` — no `description` kwarg on decorator |
| `AssetOut(io_manager_key=…)` on graph multi-assets | Unreliable; prefer **`@op(out=Out(io_manager_key=…))`** ([issue #15001](https://github.com/dagster-io/dagster/issues/15001)) |

**Practical recipe for 1.12 graph-backed assets:**

1. Keep `@graph_asset` (supports `description`, `group_name`, `ins`).
2. Do **not** use `.with_attributes(io_manager_key=…)`.
3. Put **`io_manager_key` on every inner `@op` `Out`**, including the last op whose return value is the graph output.
4. Put **`input_manager_key`** on every `AssetIn` that loads a blob-backed asset.
5. Add a unit test that asserts inner ops are not using the default `"io_manager"` key.

Example regression test:

```python
def test_pipeline_uses_adls_io_not_default_snowflake():
    assert batch_manifest.op.output_defs[0].io_manager_key == IO_MANAGER_MY_PIPELINE
    assert prepare.output_defs[0].io_manager_key == IO_MANAGER_MY_PIPELINE
    assert fan_out.output_defs[0].io_manager_key == IO_MANAGER_MY_PIPELINE
    assert run_one_batch.output_defs[0].io_manager_key == IO_MANAGER_MY_PIPELINE
    assert summarize.output_defs[0].io_manager_key == IO_MANAGER_MY_PIPELINE
```

### Checklist before you merge

- [ ] Default `io_manager` in `Definitions` matches your **table** assets (often Snowflake pandas).
- [ ] Every **`dict` / `list` handoff** uses the blob IO manager on **`@asset`**, **`AssetIn`**, and **`Out` / `DynamicOut`**.
- [ ] Graph asset **loads upstream assets** with `input_manager_key`, not only `deps=`.
- [ ] Mapped steps that launch K8s use a **concurrency key** if you need a cap on parallel jobs.
- [ ] Tests assert IO manager keys on ops (cheap, catches regressions before deploy).
- [ ] You know the difference between **op succeeded** vs **handle output failed** in the UI.

### Why this took so long in practice

The orchestration pattern from the [2024 post](/2024/09/20/parallelizing-your-workflows-with-dagster.html) was already correct. The time went into **IO wiring** and **version-specific decorator traps**:

- Mixing **warehouse IO** (DataFrames) with **orchestration IO** (pickled Python objects).
- Assuming the **graph asset decorator** would accept `io_manager_key` like `@asset` does.
- Chasing errors in **truncate / SQL** when the failure was **`handle_output`** on the next line of the log.

Once every step declares the blob IO manager explicitly, the same graph runs reliably: manifest on ADLS, dynamic map to K8s, summary back on ADLS, Snowflake only where SQL belongs.

### Conclusions

Dynamic `graph_asset` parallelism and Azure scale fit together when you treat **orchestration state** and **warehouse tables** as two storage problems. Use **ADLS pickle IO** for manifests and batch metadata across assets and inner ops; keep **Snowflake IO** for tabular assets; on Dagster 1.12, pin IO on **`@op` outputs** rather than fighting unsupported decorator kwargs.

If you have not read the first part yet, start with [Parallelizing Your Workflows with Dagster](/2024/09/20/parallelizing-your-workflows-with-dagster.html) for the `DynamicOut` / `.map()` / `.collect()` basics — this post is the Azure storage layer on top.

---

I hope this saves you the week we spent on `SnowflakeIOManager` and `with_attributes`. Questions welcome on [Twitter](https://twitter.com/MrTheodor).
