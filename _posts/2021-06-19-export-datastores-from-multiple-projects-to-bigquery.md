---
layout: post
title: "Export Datastores from multiple projects to BigQuery"
date: 2021-06-19
description: "How to export datastores from multiple projects using Google Dataflow — with additional filtering of entities."
tags:
  - gcp
  - dataflow
  - bigquery
  - apache-beam
  - data-engineering
---

---

![](https://cdn-images-1.medium.com/max/800/0*ie7aS6fZ7QOX19th)

Nieuwpoort (by author)

### Export Datastores from multiple projects to BigQuery

#### How to export datastores from multiple projects using Google Dataflow — with additional filtering of entities.

This is a short extension to my previous [story](https://towardsdatascience.com/export-datastore-to-bigquery-using-google-dataflow-1801c25ae482), where I described how to incrementally export data from Datastore to BigQuery. Here, I discuss how to extend the previous solution to the situation where you have Datastores in multiple projects. The goal remains the same, we would like to have the data in BigQuery.

[**Export Datastore to BigQuery using Google Dataflow**  
*How to employ Google Dataflow to export Datastore to BigQuery with additional filtering of entities.*towardsdatascience.com](https://towardsdatascience.com/export-datastore-to-bigquery-using-google-dataflow-1801c25ae482 "https://towardsdatascience.com/export-datastore-to-bigquery-using-google-dataflow-1801c25ae482")

Overall, the problem can be expressed with the following diagram

![](https://cdn-images-1.medium.com/max/800/1*zrZ_xTK3didXwrG-LvqKkA.png)

Sketch of the architecture (by author)

The Dataflow process can live either in one of the source projects or can be put in a separate project — I will put the dataflow process in a separate project. The results can be stored in BigQuery that is located either in the same project as the dataflow process, or in another project.

### Generalization

Let’s begin with the generalization. First, I have extended the config file with two new fields: `SourceProjectIDs` which is nothing more than a list of source GCP projects, and `Destination` that defines where the output BigQuery dataset lives.

```
SourceProjectIDs:  
  - project-a  
  - project-b  
  - project-c  
Destination:  
  ProjectID: dataflow-streaming  
  Dataset: datastore_dev
```

The extended dataflow pipeline is defined as follows:

```
rows = (  
    p  
    | 'projects' >> beam.Create(project_ids)  
    | 'get all kinds' >> beam.ParDo(GetAllKinds(prefix_of_kinds_to_ignore))  
    | 'create queries' >> beam.ParDo(CreateQuery(entity_filtering))  
    | 'read from datastore' >> beam.ParDo(ReadFromDatastore._QueryFn())  
    | 'convert entities' >> beam.Map(entity_to_json)  
)
```

It is extended with one additional step `projects` , which produces `PCollection` with a list of source projects (from the config file). A small change to the `get all kinds` step was needed. `GetAllKinds` was changed into PTransform step that for each of the project creates a list of tuples `(project_id, kind_name)` .

The `process`method of DoFn accepts tuples as any other serializable object. By this, the next step, `create queries` , creates queries to get records from specific `kind_name` that lives in the Datastore in `project_id` .

```
def process(self, project_kind_name, **kwargs):  
    """  
    :param **kwargs:  
    :param project_kind_name: a tuple with project_id, kind_name  
    :return: [Query]  
    """  
  
    project_id, kind_name = project_kind_name
```

The query produced by this step already contains `project_id` so we do no longer need to pass the project id.

The schema of JSON objects that are stored in BigQuery contains in the `__key__` field a property `project` additionally. The name of output tables in BigQuery is constructed by prefixing `kind_name` with the `project_id`.

### It’s all about permissions

The clue of the presented solution lays in the permissions. Dataflow uses two service accounts (SA), one is used during the job creation and the second is used by worker instances to access resources.

We are interested in SA that is used by the worker. By default, this service account is automatically created when the Compute Engine API is enabled for your project, and has a standard name `<project-number>-compute@developer.gserviceaccount.com`

Hence, to give your Dataflow pipeline access to Datastores that are in a different project. Therefore, in each of the source project, add account `<project-number>-compute@developer.gserviceaccount.com` to the project with the role `role/datastore.viewer` .

![](https://cdn-images-1.medium.com/max/800/1*IeQbcncufsJTI_jbpN8aKQ.png)

IAM permissions in one of the source projects (by author)

That’s all — the pipeline works as expected:

![](https://cdn-images-1.medium.com/max/800/1*oSU2TNWj-okzfKsY5Rw7rg.png)

Extended pipeline with the projects step (by author)

---

Dataflow is a powerful tool to automate your ETL process. As you can see, it can be very easily generalized to work with the sources that do not need to live in the same project as Dataflow process.

---

The story was inspired by the question asked by [Andrew Fleischer](https://medium.com/u/64c355ee755c) — thanks!

I hope you have enjoyed the story, and it could be helpful in your daily work. Feel free to contact me via [Twitter](https://twitter.com/MrTheodor) or [Linkedin](https://www.linkedin.com/in/jkrajniak/) if you have any questions or suggestions.