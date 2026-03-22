---
layout: post
title: "Parallelizing Your Workflows with Dagster"
date: 2024-09-20
description: "Parallelization of your computations is an important step in your data pipelines. Imagine you have hundreds of ML models to train or need…"
tags:
  - dagster
  - python
  - data-engineering
  - parallelization
---

---

![](/assets/images/posts/parallelizing-your-workflows-with-dagster/964d15d942.png)

Photo by [EJ Strat](https://unsplash.com/@xoforoct?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

### Parallelizing Your Workflows with Dagster

Parallelization of your computations is an important step in your data pipelines. Imagine you have hundreds of ML models to train or need to run processes over enormous datasets. If tasks can run independently on chunks of data, you can process them in parallel.

There are multiple ways to accomplish this. In scientific computing, a common approach is to use queue systems combined with the MPI programming model. This allows you to distribute your computation across many nodes.

Big data has its framework — MapReduce. The approach in this computational algorithm is to divide the dataset into subsets, distribute them across nodes, perform operations, and then collect the results. The key is that the computation should be close to the data’s location to minimize data transfer between nodes.

In serverless architectures, we have a fan-out/fan-in pattern where computation is dynamically distributed through a queue to serverless cloud functions. (You can read more about this in my previous [article](https://medium.com/nordcloud-engineering/keep-track-on-your-cloud-computations-67dd8f172479)).

In this short post, I’ll show how to use the Dagster to create such parallel computations.

### Dagster

Dagster, a next-gen orchestration platform, redefines the classic Airflow model by focusing on data assets instead of tasks. But tasks haven’t vanished entirely — we’ll still use them for parallelization here.

### Computation schema

Below you can find the general schema of the computation flow that will be implemented in this work.

![](/assets/images/posts/parallelizing-your-workflows-with-dagster/fcee457c91.png)

Computational flow (by author)

The flow is composed of three elements:

- splitter — divide the input data into n batches
- processing units — process batch of data
- collector — join results

In principle, you can implement this kind of schema in Apache Airflow. The only difficulty lies in the splitter part. Here, I assumed that the number of batches would not be constant. Instead, it will vary depending on the input data.

### Solution

I assume you’re already familiar with starting a Dagster project. If not, I recommend visiting [Dagster university](https://courses.dagster.io/).

For the sake of simplicity, I keep all the code within a single file. As for the database, I use [DuckDB](https://duckdb.org/).

The load of the data is realized by the Dagster [asset](https://docs.dagster.io/concepts/assets/software-defined-assets):

```
@asset  
def numbers(duckdb: DuckDBResource) -> pd.DataFrame:  
    with duckdb.get_connection() as conn:  
        return pd.read_sql("SELECT * FROM numbers", conn)
```

It just queries the database and gets all the data.

Then we need to split the data, this is realized by the [ops](https://docs.dagster.io/concepts/ops-jobs-graphs/ops) (this is a computational unit, that can be referred to task in Apache Airflow).

```
@op(out=DynamicOut(list))  
def load_pieces(context: OpExecutionContext, large_data: pd.DataFrame) -> Generator:  
    """Split the large data into a batches where the sum of elements in each  
    batch is less than 1000."""  
    current_batch = []  
    current_sum = 0  
    batch_idx = 0  
    for number in large_data['number']:  
        if current_sum + number > 10000:  
            yield DynamicOutput(current_batch, mapping_key=f"batch_{int(current_sum)}_batch_idx_{batch_idx}")  
            current_batch = []  
            current_sum = 0  
            batch_idx += 1  
        current_batch.append(number)  
        current_sum += number  
      
    batch_idx += 1  
    if current_batch:  
        yield DynamicOutput(current_batch, mapping_key=str(batch_idx))  
        context.log.info(f"Yielded batch {batch_idx}: {current_batch} {current_sum}")
```

The input is a sequence of numbers. We want to split this sequence into batches where the sum of the numbers in each batch is less than 10000.

The next step is to define the computation units that will process each batch of numbers. I define two computation units, just to make the flow a bit more complex.

```
@op  
def power(number: int) -> int:  
    return number**2  
  
@op  
def compute_piece(piece: list[int]) -> list[int]:  
    return [power(x) for x in piece]  
  
@op  
def compute_piece_2(piece: list[int]) -> list[int]:  
    return [power(x) for x in piece]
```

Both operations do the same thing: square each number.

The final step is to combine the batches into a single output list. This is done by the following ops:

```
@op  
def merge_and_analyze(pieces: list[list[int]]) -> int:  
    return sum([sum(piece) for piece in pieces])
```

This task sums the values from each batch.

The final component is the actual job that will utilize these ops to compute the results.

```
@graph_asset  
def my_job(numbers: list[int]) -> int:  
    # large_data = numbers()  
    pieces = load_pieces(numbers)   
    results = pieces.map(compute_piece)  
    results = results.map(compute_piece_2)  
    result = merge_and_analyze(results.collect())  
    return result
```

`graph_asset` is a composition of ops that generates the asset.

The complete flow presented by Dagster is shown below.

![](https://cdn-images-1.medium.com/max/800/1*EAY8L_vU_WuZCrt5g_ZrpQ.png)

Dagster computation flow

Dagster’s user interface provides a clear visualization of the computation graph, as shown below.

![](https://cdn-images-1.medium.com/max/800/1*ClJm-Kn1ygvtAdvuLKuUgQ.png)

Dagster user interface

---

The complete code

```
from typing import Generator  
from dagster import Definitions, DynamicOut, DynamicOutput, OpExecutionContext, asset, graph_asset, op  
from dagster_duckdb import DuckDBResource  
from numpy.random import f  
import pandas as pd  
  
@asset  
def numbers(duckdb: DuckDBResource) -> pd.DataFrame:  
    with duckdb.get_connection() as conn:  
        return pd.read_sql("SELECT * FROM numbers ORDER BY numbers", conn)  
  
@op(out=DynamicOut(list))  
def load_pieces(context: OpExecutionContext, large_data: pd.DataFrame) -> Generator:  
    """Split the large data into a batches where the sum of elements in each  
    batch is less than 1000."""  
    current_batch = []  
    current_sum = 0  
    batch_idx = 0  
    for number in large_data['number']:  
        if current_sum + number > 100000:  
            yield DynamicOutput(current_batch, mapping_key=f"batch_{int(current_sum)}_batch_idx_{batch_idx}")  
            current_batch = []  
            current_sum = 0  
            batch_idx += 1  
        current_batch.append(number)  
        current_sum += number  
      
    batch_idx += 1  
    if current_batch:  
        yield DynamicOutput(current_batch, mapping_key=str(batch_idx))  
        context.log.info(f"Yielded batch {batch_idx}: {current_batch} {current_sum}")  
  
@op  
def merge_and_analyze(pieces: list[list[int]]) -> int:  
    return sum([sum(piece) for piece in pieces])  
  
  
@op  
def power(number: int) -> int:  
    return number**2  
  
@op  
def compute_piece(piece: list[int]) -> list[int]:  
    return [power(x) for x in piece]  
  
@op  
def compute_piece_2(piece: list[int]) -> list[int]:  
    return [power(x) for x in piece]  
  
@graph_asset  
def my_job(numbers: pd.DataFrame) -> int:  
    pieces = load_pieces(numbers)   
    results = pieces.map(compute_piece)  
    results = results.map(compute_piece_2)  
    result = merge_and_analyze(results.collect())  
    return result  
  
  
  
defs = Definitions(  
    assets=[numbers, my_job ],  
    jobs=[],  
    resources={  
        "duckdb": DuckDBResource(  
            database="duck.duckdb",  # required  
        ),  
    },  
)
```

### Conclusions

In this post, I showed how to use Dagster’s capabilities to implement parallel computations, a crucial aspect of efficient data processing pipelines. I showed a workflow where data is split into batches, processed concurrently, and then aggregated. While Apache Airflow could handle similar scenarios, Dagster’s focus on data assets and its intuitive interface simplifies the process, especially when dealing with dynamic batch sizes.

---

I hope you have enjoyed the story, and it could be helpful in your daily work. Feel free to contact me via [Twitter](https://twitter.com/MrTheodor), if you have any questions or suggestions. You can also support me by [buying me a coffee](https://buymeacoffee.com/jkrajniak).