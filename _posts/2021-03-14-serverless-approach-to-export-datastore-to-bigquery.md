---
layout: post
title: "Serverless approach to export Datastore to BigQuery"
date: 2021-03-14
description: "An easy way to periodically export your Datastore to BigQuery using a serverless approach on Google Cloud Platform"
tags:
  - gcp
  - serverless
  - bigquery
  - datastore
  - terraform
---

---

![](https://cdn-images-1.medium.com/max/1200/0*R6zM_t5eWmE9YfM-)

Photo by [Maksym Kaharlytskyi](https://unsplash.com/@qwitka?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

### Serverless approach to export Datastore to BigQuery

#### An easy way to periodically export your Datastore to BigQuery using a serverless approach on Google Cloud Platform

A bit of overview, [Google Datastore](https://cloud.google.com/datastore) is a fully managed [NoSQL](https://en.wikipedia.org/wiki/NoSQL) service available in Google Cloud Platform since 2008. It can be treated as a key-value as well as a document database, provides an SQL-like query language and SDK with bindings to many programming languages.

The database is organized into Entities (or records). Each of them can have one or more named properties, where each of them can have one or more values. An entity is identified by the key which consists of namespace, kind and identifier (a string or an integer). The key can be used by the application to fetch a specific entity. It is worth noting that entities of the same kind do not need to have the same properties, and the values for the same-named property across do not need to have the values of the same type. Shortly speaking, you can store any document you like under the key.

Although Datastore allows querying kinds, from the data exploration and analytical perspective it is more feasible to have the records in a regular database that is easily queryable, for example, [BigQuery](https://cloud.google.com/bigquery).

### Let’s start

One of the possible solutions is to export the kinds from datastore to BigQuery. The export is done in two steps:

1. Export selected kind to the bucket in Cloud Storage
2. Import exported kind from Cloud Storage to BigQuery

[BigQuery loading job has the option to directly read the exported Datastore kinds from Cloud Storage](https://cloud.google.com/bigquery/docs/loading-data-cloud-datastore#:~:text=BigQuery%20supports%20loading%20data%20from,into%20BigQuery%20as%20a%20table.), so we do not need any other transformation. The constraint from the BigQuery load job is that the kinds have to be exported one by one. It is also worth noting that the existing exported table in BigQuery will be replaced with the new data.

The solution is simple but it has some drawbacks. The major one is that the procedure does not allow to specify the subset of records in the kind to be exported. In other words, you are forced to export-import all records each time. For small datastore, this is still feasible but for bigger databases, this solution won’t be optimal — be aware of this. In the next post, I will show you how to solve it — stay tuned.

For multiple kinds a simple optimization technique would be to overlap the export/import jobs, as shown below:

![](https://cdn-images-1.medium.com/max/800/0*0KMG2wY89gLKu9of)

Overlap of parallel export/import jobs (by author)

By this, we can reduce the overall time to export the whole Datastore. Keep in mind that you are limited to have 50 concurrent export jobs, and you can do up to 20 export requests per minute for a project.

### Command-line approach

The export/import can be run using two command-line tools: [*gcloud*](https://cloud.google.com/sdk/gcloud)and [*bq*](https://cloud.google.com/bigquery/docs/bq-command-line-tool)*.* With the first one, you will run the export of the datastore to the bucket: `gcloud datastore export gs://bucket-name/Kind1 --project gcp-project --kinds Kind1`

With the second, you can run the job import in BigQuery that will fetch the data from the bucket:   
`bq load --source_format=DATASTORE_BACKUP datastore_export.Kind1 gs://bucket-name/Kind1/default_namespace/kind_Kind1/default_namespace_kind_Kind1.export_metadata`

### Serverless approach

The command-line approach sounds like a good point to start, to explore if the solution is working, as a one-time export method to have immediate data in BigQuery. However, if you like to run this task every day, it is better to schedule this job somewhere else.

Although the above two commands could be executed from a [virtual machine](https://cloud.google.com/compute), with cron etc, this isn’t an optimal solution. First, you will wast resources if the task has to be run e.g. every day, as the resources will be used only for a few minutes each day. Secondly, you have to monitor if the VM is running, if the system is up-to-date, etc. And here comes a serverless.

[Serverless](https://en.wikipedia.org/wiki/Serverless_computing) is a popular concept where you delegate all of the infrastructure tasks elsewhere. And what you as a developer has to provide is only the code that solves your problem. So, you do not need to manage virtual machines, upgrading the host operating systems, bother about networking etc. — this is all done by a cloud provider.

---

In this short story, I will show how to build the export/import procedure using serverless components. This is possible because in the end we will only call [GCP](http://cloud.google.com/) APIs and wait for the results — the work will be done in the background.  
The architecture diagram of the solution is shown below.

![](https://cdn-images-1.medium.com/max/800/1*FicdIyE4kA0CNwFS-shCLg.png)

The architecture diagram of the serverless solution (by author)

The architecture comprises two [cloud functions](https://cloud.google.com/functions):

- datastore\_exporter
- bigquery\_importer

The *datastore\_exporter* is responsible for scheduling datastore export of the input kind. The next function, *bigquery\_importer*, is responsible for scheduling the BigQuery load job.

The other components of the diagram are used to orchestra the process. Let me shed light on how it works in details, by enlisting it step-by-step.

### Function datastore exporter

The cron-like job is governed by [Google Scheduler,](https://cloud.google.com/scheduler) which triggers *datastore\_exporter* cloud function, which inside list all possible type of kinds in the datastore and for each of them, schedules the export to Cloud Storage. The resulting objects are located in the Cloud Storage bucket.

The schedule itself is created with

We define that the function will be executed every day at 6.00. The scheduler will trigger the cloud function by calling an HTTP trigger. It uses an associated service account to authenticate the request.

The definition of a service account used by schedule is shown below. The account has permission to invoke *datastore\_exporter* cloud function.

The *gcf\_datastore\_exporter* function is defined with

where we set that the function will be triggered by HTTP. As of 15 January 2020, the Cloud Functions by default requires [authentication to be triggered](https://cloud.google.com/functions/docs/securing/managing-access-iam#allowing_unauthenticated_function_invocation). We keep that untouched.

When the export of a given kind is completed, an [event](https://cloud.google.com/functions/docs/calling/storage) *google.storage.object.finalize* is raised which is captured by *bigquery\_importer* function.

### Function BigQuery importer

The purpose of this function is to handle bucket event and schedule the import of exported datastore to BigQuery.

The function itself is defined using [*google\_cloudfunctions\_function*](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloudfunctions_function)resource

where we define that the function will be triggered on the events from the datastore output bucket. We are only interested in the events *google.storage.object.finalize.*

The body of the function is pretty straightforward.

The function is listening to all object finalize events, but only when the object of name *all\_namespaces\_kind\_<kind>.export\_metadata* is created then the import to BigQuery is scheduled.

The function responsible for running the BigQuery import is straightforward. What we in fact have to define is a job, which basically contains the same attributes as the command line:

*The full function you can find here:* [*https://github.com/jkrajniak/demo-datastore-export*](https://github.com/jkrajniak/demo-datastore-export)

[**jkrajniak/demo-datastore-export**  
*Contribute to jkrajniak/demo-datastore-export development by creating an account on GitHub.*github.com](https://github.com/jkrajniak/demo-datastore-export "https://github.com/jkrajniak/demo-datastore-export")

### Permissions

A proper permission set is very important, and we should always follow the [principle of the least privileges](https://en.wikipedia.org/wiki/Principle_of_least_privilege). Both cloud functions have their own [service accounts](https://cloud.google.com/iam/docs/service-accounts). For the datastore exporter, we attach the following roles

```
"roles/monitoring.metricWriter",  
"roles/logging.logWriter",  
"roles/datastore.importExportAdmin",  
"roles/datastore.viewer"
```

The second function needs the following permissions

```
"roles/monitoring.metricWriter",  
"roles/logging.logWriter",  
"roles/bigquery.jobUser",
```

Moreover, it needs access both to the output bucket and output dataset. This is done by binding IAM permissions

### Deployment

A few words on the deployment of these two cloud function. As other parts of the “infrastructure” are built-in terraform, I thought that the deployment of Cloud Function should be also covered by [Terraform](https://www.terraform.io/) (TF). For this, I used two TF resources *archive\_file* and *google\_storage\_bucket\_object.*

The [*archive\_file*](https://registry.terraform.io/providers/hashicorp/archive/latest/docs/data-sources/archive_file) resource will create a zip file from the content of the source directory. Then this file will be copied to Cloud Storage. Here, the objects in Cloud Storage has a suffix that is computed from the SHA1 of the file — this works as simple versioning. For the production run, I would use Git commit hash and git tags for the object suffix.

On <https://github.com/jkrajniak/demo-datastore-export> you will find code for the infrastructure and two Cloud Functions.

---

A few points at the end

1. I always encourage using a serverless approach. It’s simply easier and faster to focus only on the method and leave all the infrastructure troubles on the giant's shoulders.
2. Always put your infrastructure as a code, e.g. using AWS [CloudFormation](https://aws.amazon.com/cloudformation/), [Terraform](https://www.terraform.io/) or [CDK](https://aws.amazon.com/cdk/). It is simply more reliable and reproducible than any other methods of handling project/service configuration. You will immediately benefit from this approach whenever you will have to recreate infrastructure in a new GCP project, or simply something will be broken. Besides, by this, you can automate the deployment of infrastructure changes in the same way as you handle the deployment of your application.
3. Data engineering tasks shouldn’t be an exception to any regular and standard way of software development — write unit tests, use CI/CD for code and infrastructure deployment and keep your code in the repository; do not rely on a solution that was clicked in any even fancy web interfaces.

---

I hope you have enjoyed the story, and it could be helpful in your daily work. Feel free to contact me via [Twitter](https://twitter.com/MrTheodor) or [Linkedin](https://www.linkedin.com/in/jkrajniak/) if you have any questions or suggestions.