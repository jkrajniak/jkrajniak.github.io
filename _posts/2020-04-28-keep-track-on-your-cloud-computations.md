---
layout: post
title: "Keep track on your cloud computations"
date: 2020-04-28
description: "How to track you distributed computation among unlimited number of functions using serverless components."
tags:
  - aws
  - serverless
  - distributed-systems
  - lambda
  - dynamodb
---

---

![](https://cdn-images-1.medium.com/max/800/1*kjQXb3ZOk9gebqEBTyRMRw.png)

### Keep track of your cloud computations

Increasing interested in using small computation units enclosed in AWS Lambda, Azure Functions, or GCP Cloud functions brings back the old problem of detecting the termination of the computation task, which is distributed among a vast amount of sub-processes.

Let us jump directly into the problem by analysing the following computation scheme

![](https://cdn-images-1.medium.com/max/800/0*9EwR7FPkUpUWsZcd)

It is composed of three parts: *splitter, sub-processes, and collector.* By design, the sub-processes are the stateless functions that take input data and produce output(s). Hence, they do not have a notion about the whole computing process. Moreover, we also impose that the collector and splitter are stateless functions.

We can establish two synchronization points: *splitter* and *collector.* The barrier at splitter is trivial. At this point, we divide input data into chunks and distribute among sub-process. The problem arises with the synchronization at the *collector.* We can say that whole computation performed by sub-processes riches barrier only when all of the sub-process is completed. But how can we know that every of sub-processes completes the job?

Let first assign to each of the sub-process a *state* property, which can have two values: *pending* and *done.* The state is assigned to the sub-process in the *splitter* and updated when the computation results are received by *collector*. We can say the computation is done whenever all of the sub-processes are in state *done.*

The *state* can be stored in the form of lookup table indexed by unique sub-process id. To complete the design, we should also assign a unique id to the whole computation process. By this, we can have multiple computations running in parallel that consists of multiple sub-processes. Therefore, the lookup table contains *sub-process-id → (state, computation-id)* tuples.

Below is the extended computation scheme with additional elements mentioned previously.

![](https://cdn-images-1.medium.com/max/800/0*5kwE35Drhr_2SZJ4)

The state of the computation (labelled by *job-id*) is monitored by the additional component *state-observer*. It periodically queries the lookup table and counts the number of sub-processes that are in state *pending.* If the result of the query is zero the whole *computation* is considered to be *completed.* Moreover, the update of the state is recorded with the timestamp. This allows to use of a last-resort method, basically *timeout* the computation job.

### Example

Let us consider a simple system, in which we have a pile of documents in S3 bucket, and we would like for each of the document get the frequency of words appearing in the document.

We demonstrate the implementation using the components of the AWS public cloud. However, all of the components can be found in Azure or GCP clouds.

The diagram below shows the architecture of the solution. It basically reflects the general computation scheme showed above.

![](https://cdn-images-1.medium.com/max/800/1*afQj8BCEO5RQU8ZEndowqw.png)

The idea behind this example is rather simple. There is a bucket that contains a bunch of text documents to process. We would like to calculate the word frequency in each of the document and store such a map (word→freq) for each of it in an output bucket. We will not describe the whole code, it is available in my [GitHub project](https://github.com/jkrajniak/demo-parallel-processing/tree/master)— only the key components.

#### Process state table

The track about the state of sub-processes is kept in the DynamoDB table with the following definition:

```
Hash key: job_id  
Sort key: process_id
```

and GSI (global secondary index) defined as

```
Hash key: job_id  
Sort key: state__process_id
```

The key point lays in the GSI, precisely in the sort key which is a concatenation of the process state and `process_id`. With that, we can very easily and fast get the number of processes in a given state by calling:

#### Observer

The observer is a lambda that periodically counts the number of processes (using the DynamoDB query on GSI — the code is above) in the *pending* state (for the requested `job_id`). This is realized by combining the queue with a certain delay (30 seconds here) and attached lambda function.

![](https://cdn-images-1.medium.com/max/800/1*RD5_4s1D9E3aGhzWItEpQw.png)

The delay on the SQS queue can be achieved by `DelaySeconds` property. If all of the processes are done then the observation is done and the message is sent to the SNS topic:

```
{  
  "job_id": "job-identifier",  
  "status": "job-status  
}
```

#### Splitter

This module gets on the input queue the request:

```
{  
  "job_id": "job identifier",  
  "bucket": "bucket-to-scan",  
  "output_bucket": "bucket-to-store-word-freq"  
}
```

where `job_id` is an identifier of the whole computation (and returned with the notification from the observer), `bucket` the S3 bucket to scan for the documents to process and `output_bucket` where the frequencies are stored.

---

We have shown how to detect and track the progress of distributed competition using very basic components found in public provides. The solution presented here does not only work with a single layer of *sub-processes* but it is also capable to track multilayer computation schemes. The drawback of using the observer pattern is the delay between the actual end of computation and the detected.