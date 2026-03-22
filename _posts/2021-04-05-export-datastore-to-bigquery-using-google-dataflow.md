---
layout: post
title: "Export Datastore to BigQuery using Google Dataflow"
date: 2021-04-05
description: "How to employ Google Dataflow to export Datastore to BigQuery with additional filtering of entities."
tags:
  - gcp
  - dataflow
  - bigquery
  - apache-beam
  - data-engineering
---

---

![](https://cdn-images-1.medium.com/max/800/1*AM6GIySotyiDsMR69fLtcQ.jpeg)

Puerto de la Cruz (by author)

### Export Datastore to BigQuery using Google Dataflow

#### How to employ Google Dataflow to export Datastore to BigQuery with additional filtering of entities

In the last story, I showed how to build a serverless solution to export all kinds from Datastore to BigQuery. The approach presented in that article is completely valid and works for even large datastore. However, the main drawback is that each time we export all rows from the datastore to BigQuery. And for a large datastore, this could create unnecessary costs and consume more time than is needed.

[**Serverless approach to export Datastore to BigQuery**  
*An easy way to periodically export your Datastore to BigQuery using a serverless approach on Google Cloud Platform*towardsdatascience.com](https://towardsdatascience.com/serverless-approach-to-export-datastore-to-bigquery-4156fadb8509 "https://towardsdatascience.com/serverless-approach-to-export-datastore-to-bigquery-4156fadb8509")

One of the ways to solve it could be a stream of updates to the database. For example, [AWS DynamoDB](https://aws.amazon.com/dynamodb/) offers [streams](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html) that can be easily linked with AWS Lambdas. A very similar feature can be found in [Google Firestore](https://cloud.google.com/firestore) (named to be the [next generation](https://cloud.google.com/datastore/docs/firestore-or-datastore) of Datastore), where a change to the document triggers Cloud Function — [see docs.](https://cloud.google.com/functions/docs/calling/cloud-firestore)

Although datastore does not offer any streaming capabilities, we can still try to solve the problem by using a query. The datastore [import/export](https://cloud.google.com/datastore/docs/export-import-entities) does not support natively filtering on the entities. Therefore, we have to do it *manually.* The procedure can be as follows:

1. Filter entities, export them to JSON and store them in Cloud Storage
2. Load JSONs from Cloud Storage to BigQuery

Let me employ to this task Google Dataflow.

Google Dataflow is a managed solution to execute different data processing schemas, like ETL, batch and stream processing. But Google Dataflow is one o the possible realization of [dataflow model](http://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf). The SDK that is used to describe the processing is implemented under the framework [Apache Beam](https://beam.apache.org/).

### Dataflow pipeline

Dataflow model is organized around the pipeline, which is your data processing workflow from start to end. Inside the pipeline two objects are important. PCollection represents a distributed data set, and PTransform represents a processing operation on PCollection.

![](https://cdn-images-1.medium.com/max/800/1*0sWx6tm7plrmc_8j09IIeA.png)

Overview on pcollection/ptransform (by author)

I will use Python as the programming language. But, the pipeline can be built in Java and Golang as well. The full working example is available in GitHub project (<https://github.com/jkrajniak/demo-datastore-export-filtering>). Here, I will only comment on important blocks of code.

[**jkrajniak/demo-datastore-export-filtering**  
*Contribute to jkrajniak/demo-datastore-export-filtering development by creating an account on GitHub.*github.com](https://github.com/jkrajniak/demo-datastore-export-filtering "https://github.com/jkrajniak/demo-datastore-export-filtering")

#### Pipeline

Let’s start building the pipeline:

```
with beam.Pipeline(options=pipeline_options) as p:  
    # Create a query and filter
```

This will create a pipeline `p` with options stored in `pipeline_options` . Next, the operator `|` will be used to join each of the *PTransform* blocks

```
rows = p | 'get all kinds' >> GetAllKinds(project_id, to_ignore)
```

This is the first stage, it will read all kinds from the datastore in a given project and produce a PCollection from that list. Internally this block implements `expand` method (below). In addition, filtering is done to remove some kinds that we do not want to be exported. In the end,`Create` [transform](https://github.com/apache/beam/blob/master/sdks/python/apache_beam/transforms/core.py#L2906) is used to build a PCollection from the list of kinds.

Next, for each of the kind, we have to build a query — this is realized by the next PTransform block `'create queries'`

```
rows = (p   
        | 'get all kinds' >> GetAllKinds(project_id, to_ignore)  
        | 'create queries' >> beam.ParDo(CreateQuery(project_id, param))  
       )
```

We use `ParDo`, which is a generic parallel processing transform block. It accepts an object derived from `beam.DoFn` class, that has to implement the method `process(self, *args, **kwargs)` . Below is the implementation of `process` method of `CreateQuery` class.

```
def process(self, kind_name, **kwargs):  
    """  
    :param **kwargs:  
    :param kind_name: a kind name  
    :return: Query  
    """  
  
    logging.info(f'CreateQuery.process {kind_name} {kwargs}')  
  
    q = Query(kind=kind_name, project=self.project_id)  
    if kind_name in self.entity_filtering:  
        q.filters = self.entity_filtering[kind_name].get_filter()  
  
    logging.info(f'Query for kind {kind_name}: {q}')  
  
    yield q
```

The method above is responsible for generating the query to fetch the elements based on the filtering parameters. A simple YAML config file is used to define the filtering options

One important note to this solution. The entities in Datastore need to have some field that can be used for getting a subset of records. In this example, we set that the field `timestamp` will be used to fetch the subset of the records. If the pipeline is executed once a day then the records match a query`(endTime-24h)<= timestamp < endTime` will be selected. You can imagine any other types of queries, not only based on timestamp. For example, you can store somewhere the id of the last fetched record, and next time fetch only records greater than the stored id.

Next, we add three more elements to the pipeline:

- apply query and fetch entities
- convert entities to JSON
- save JSONs to BigQuery

The last two stages in the pipeline are pretty obvious:

*read from datastore* fetch entities from Datastore using the queries created in the previous step. As a result, a PCollection of entities from the datastore is created. Next, each of the entities is converted to JSON representation in `beam.Map(entity_to_json)` . `beam.Map` is a special case of `beam.ParDo`. It takes a single element from PCollection and produced a single element.

The last element of the pipeline is the output PTransform. The entities from the kinds that weren’t subject to the filtering are directed to an empty table. The other, which are possessed from filtering, are appended to the existing table. To direct the elements into these two outputs, we use a [tagging feature](https://beam.apache.org/documentation/programming-guide/#additional-outputs) that allows producing multiple PCollections.

If the kind name is in the options to filter then we tag the element by `write_append` otherwise, we attache `write_truncate` tag to the element.

Next, we write these two split collections to BigQuery:

In each of the write methods, we use `SCHEMA_AUTODETECT` option. The output table names are dynamically derived from a kind name — if needed to be created.

If you run the pipeline in Google Dataflow then the entire job is visualized as below:

![](https://cdn-images-1.medium.com/max/800/1*X4tcr1FtRMHd9Wicd1x-dA.png)

Data pipeline (by author)

---

So actually what is happening under the hood when you call the command to run the pipeline. Basically, if you do it with the runner`direct` the workflow will run obviously on your local machine.

With a runner `dataflow` , the workflow will be executed in GCP. First, your code of the pipeline is packed as a PyPi package (you can see in the logs that command `python setup.py sdist` is executed), then the `zip` file is copied to Google Cloud Storage bucket. Next workers are setup. The workers are nothing more than [Google Cloud Compute](https://cloud.google.com/compute) instances. You can even see them in the Cloud console:

![](https://cdn-images-1.medium.com/max/800/1*vSMro0WWwPtw5codnpQGPQ.png)

and, if you need, you can ssh into them. Be aware, that it takes time to spin up the workers, download and install your pipeline on the workers.

> [In fact, the newest feature in Dataflow provides a custom Docker container image.](https://cloud.google.com/dataflow/docs/guides/using-custom-containers) This allows you to reduce the worker start time (all dependencies can be already packed into the image), you can use third-party libraries that are not publicly available, or you can run some software in the background — sky is the limit.

When the code is installed on the workers, the pipeline is executed.

---

#### Why not pure Cloud Function?

Let me just discuss why Google Dataflow and not pure Cloud Functions. Cloud Function could be a completely valid solution, but in the end, the architecture and maintenance would be very difficult. First, in contrast to the full-load mode, here we have to physically fetch the records and store them in Cloud Storage. The limits on a function are 4096 MB of memory and maximum runtime o 9 minutes. So to have a robust and scalable solution we have to run multiple functions on the batch of records. You can imagine the tree of parallel execution as for each of the page results a function is executed to fetch a subset of records. Then the records in parallel will be converted to JSON and loaded to BigQuery

To track the progress of the parallel execution, a similar solution to the one I showed in one of [my previous](https://medium.com/nordcloud-engineering/keep-track-on-your-cloud-computations-67dd8f172479) posts could be used

[**Keep track on your cloud computations**  
*How to track you distributed computation among unlimited number of functions using serverless components.*medium.com](https://medium.com/nordcloud-engineering/keep-track-on-your-cloud-computations-67dd8f172479 "https://medium.com/nordcloud-engineering/keep-track-on-your-cloud-computations-67dd8f172479")

or [Google Workflow](https://cloud.google.com/workflows). Although it is feasible to organize, I believe the effort is not worth the possible cost reduction.

#### Pricing

Well, you pay for the execution time (billed per second increments) and for the resources. The pipeline has at least one worker, which consumes vCPU, memory, storage and optionally GPU. If your tasks are not so computational and storage-intensive then you can change the default settings by adjusting WorkerOptions. By default, the disk size of the worker for batch processing is set to 250 GB and for stream processing to 400 GB. If your processing can fit into the memory then this is a quite big number. In the above example, I have used 25 GB of disk size per worker — it was enough.

![](https://cdn-images-1.medium.com/max/800/1*9L-qhNX_IYFzuT8xG27lLw.png)

Price estimation, two workers, 25GB per worker, monthly vCPU 1 hour (by author)

---

Google Dataflow and Apache Beam model are a powerful data engineering tool that allows building complicated data pipelines. It can be used both for batch and stream processing, with different input sources and output destination. Moreover, the work is effectively distributed seamlessly among the workers, without any tuning.

---

I hope you have enjoyed the story, and it could be helpful in your daily work. Feel free to contact me via [Twitter](https://twitter.com/MrTheodor) or [Linkedin](https://www.linkedin.com/in/jkrajniak/) if you have any questions or suggestions.