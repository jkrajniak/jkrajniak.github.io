---
layout: post
title: "Watch your stream"
date: 2020-09-10
description: "In the last story, I have discussed how to observe distributed cloud computation. Here, I will focus..."
tags:
  - serverless
  - distributedsystems
  - aws
  - cloud
canonical_url: "https://dev.to/jkrajniak/watch-your-stream-1d7p"
image: "/assets/images/posts/watch-your-stream/b999c46f59.jpg"
---

In the [last story](https://medium.com/nordcloud-engineering/keep-track-on-your-cloud-computations-67dd8f172479), I have discussed how to observe distributed cloud computation. Here, I will focus on a bit similar topic. Mainly, how to observe your stream of data flowing into your system, precisely how to decide that at a certain moment there won't be any more data flowing, and we are ready to do the post-processing.

This perhaps sounds in contradiction to the common approach in dealing with streams, where one could expect to process elements one-by-one. But let us consider the following situation:

1. An initial event invokes a set of producers to push data into a stream;
2. Producers simultaneously push data to the stream. Let then assume that the consumer stores the records in some permanent storage like S3;
3. Only after all expected data are in permanent storage, we can run the next transformation, e.g. some aggregations;

A very simple approach would be to track the execution of the producers (e.g. using the method which I showed in my [previous story](https://medium.com/nordcloud-engineering/keep-track-on-your-cloud-computations-67dd8f172479)). The third step will be executed only if all of the producers finish computations. 

The major drawback of this approach is not taking into account any delays related to passing records through the stream and storing them in permanent storage. This could, in the end, leads to computing aggregations on a partially completed data set.

---

A better idea could be to use an observer to track the number of records that are stored permanently in the storage.
Let us consider the following architecture, using a common component from AWS: Kinesis Firehose, S3, Lambda, DynamoDB.
The overall diagram is shown below

![Architecture Diagram](/assets/images/posts/watch-your-stream/b30165529f.png)

We have a bunch of lambdas which produce some data and push them to Kinesis Firehose. This is then stored in S3 bucket.
A *monitor* lambda is triggered whenever Firehose creates a new object in S3 bucket. We count such events and update the counter in DynamoDB table. The primary key of the record is the observed bucket name.

A prototype handler for such event can be defined as follows:
```python
import boto3
import os

dynamodb = boto3.resource('dynamodb')

observerTableName = os.environ.get('observerTableName')
table = dynamodb.Table(observerTableName)


def monitor(event, context):
    for record in event.get('Records', []):
        if record.get('eventName', '') == 'ObjectCreated:Put':
            bucketName = record['s3']['bucket']['name']
            table.update_item(
                Key={'id': bucketName},
                UpdateExpression='ADD num_records :val',
                ExpressionAttributeValues={':val': 1}
            )

```

A second part of the diagram is the *observer*.
This lambda uses a SQS queue to run recurrently and reads the content of the *storage counter* DynamoDB table.
The algorithm behind the observer is quite simple and can be described by the following diagram
![Window observer](/assets/images/posts/watch-your-stream/31ce11b059.png)

It can be implemented as follows
```python
def observer(event, context):
    for record in event['Records']:
        payload = record['body']
        message = json.loads(payload)
        if message.get('repeated', 0) >= MAX_NUM_REPEAT:
            # call external service, ready to handle the data in storage.
            print(f'{message=} finished - calling external service')
            continue

        res = table.get_item(Key={'id': message['bucket']})
        if 'Item' in res:
            item = res['Item']
            num_records = int(item['num_records'])
            if num_records == message['last_num_records']:
                message['repeated'] += 1
            else:
                message['repeated'] = 0  # Reset the repeat counter.
            message['last_num_records'] = num_records
            sqs.send_message(QueueUrl=os.environ['selfSQSURL'], MessageBody=json.dumps(message), DelaySeconds=30)
```
with the SQS message in the following structure
```json
{
  "repeated": 0,
  "last_num_records": 0,
  "bucket": "bucket name"
}
```

Two parameters have to be adjusted. The first is the length of the observation window (declared in the above code as `MAX_NUM_REPEAT`). The second parameter is the delay between reads from the DynamoDB table, here set to `30` seconds.

Let me comment on these two parameters.
If the producer is a slow process, and we sample too fast (with short delay time), then we can falsely consider the process to be finished.
On the other hand, if the *producer* is a fast process, we can unnecessarily wait `MAX_NUM_REPEAT * delay` seconds before the *observer* sends a notification that the data are ready.

You can use different optimization strategies for the delay time:

* divide initial delay time by the `repeated` counter
    ```python 
    delay = 30 if repeated == 0 else int(30 / repeated)
    ```

* using exponential function
    ```python
    delay = numpy.ceil(30*numpy.exp(-repeated)).astype(int)
    ```

It depends on the nature of the production process which parameters are appropriate.

---

The method I have presented here can be useful in data processing, where we need to run some post-processing tasks after we have a dataset ready in the storage (like S3, Elasticsearch, etc.).
It needs some tuning to be applicable, and one has to consider as well, how to deal with any false-positive cases.

---

*On the cover image, the Dijle river near Leuven, Belgium*

---

If you liked the post, then you can [buy me a coffee](https://www.buymeacoffee.com/jkrajniak). Thanks in advance.