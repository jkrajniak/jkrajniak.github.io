---
layout: post
title: "Efficient message broadcasting with SNS filtering"
date: 2026-03-21
description: "Broadcasting messages from one source to multiple destinations (or consumers) is a commonly seen pattern in distributed computing…"
tags: []
---

---

![](https://cdn-images-1.medium.com/max/800/0*aZzhvoSOi1TYyDGw.jpg)

Oranjemolen, Vlissingen (by author)

### Efficient message broadcasting with SNS filtering

Broadcasting messages from one source to multiple destinations (or consumers) is a commonly seen pattern in distributed computing solutions.  
 A very simple case is when we would like to trigger multiple workers at the same time to run a parallel job. The trigger can be executed, e.g., as a *CloudWatch cron-like event*.

![](https://cdn-images-1.medium.com/max/800/1*VEt8ZaUVoLznLwjPJUE5DQ.png)

Simple broadcasting (by author)

Here, the same message is delivered to multiple consumers. In terms of a specific implementation, using AWS cloud components, the above diagram can be transformed into the following architecture diagram:

![](https://cdn-images-1.medium.com/max/800/1*PzZ1KPsKkcppR6CkzvnR3g.png)

Broadcasting with SNS topic and AWS lambdas (by author)

Now, let say that we would like that pattern an event bus, on which messages to different consumers are published into the same communication channel, as depicted in the figure below.

![](https://cdn-images-1.medium.com/max/800/1*huxotsMOP_-TETr5JHkSWQ.png)

Message bus (by author)

The communication channel could be, e.g. SNS topic, and the consumers, as in the previous example, can be an AWS Lambdas. Multiple producers (marked with different colours) push messages to the communication bus and the consumers read the messages from it.

This solution has one major drawback, the same message will be delivered to multiple consumers, even if the consumer cannot handle that message. So for example, an *orange* consumer will receive a message marked with *green*, or *red*. In principle, nothing bad could happen if the consumers can filter out such messages. However, this will involve additional computational time and cost.

We could think about several solutions to this kind of problem. The filtering, as said before, can be delegated to the consumers. There could be multiple communication channels, one per every message type, so the consumers can be linked directly with the appropriate channel. But on the cost of complicated architecture.

---

Instead of making the architecture complex, or move the filtering to the consumer code, we could use [message filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html) available in the SNS service. By this, the consumers can get only a subset of the messages that are pushed to the topic.

The filtering is done on the attributes and values of the attributes assigned to the published message. A very basic example, using a [serverless framework](https://serverless.com), is shown below

```
functions:  
  hndl1:  
    handler: handler.fun1  
    events:  
     - sns:   
          arn: !Ref NotifyTopic  
          topicName: notifyTopic  
          filterPolicy:  
            messageType:  
              - hndl1  
            messageContext:  
              - running
```

Here, the lambda hndl1 will be triggered by an incoming message on SNS topic only if the message will have two attributes: `messageType`, `messageContext` of values `hndl1`, `running` respectively.

Currently, SNS policy filtering can handle only attributes of types: `String`, `String.Array` and `Number`.  
 The filter values can be either matched exactly or treated as prefixes. In the previous example, the values were matched exactly. In the following example, we use keywords `prefix` to indicate that the value should be treated as a string prefix. Moreover, the keyword `anything-but` allows defining the values the attribute should not have (blacklist).

```
functions:    
  hndl2:  
    handler: handler.fun2  
    events:  
      - sns:   
          arn: !Ref NotifyTopic  
          topicName: notifyTopic  
          filterPolicy:  
            messageType:  
              - hndl2  
            messageContext:  
              - incontext  
              - prefix: type_  
            messageStage:  
              - anything-but:  
                  - restart
```

It is worth mentioning that `prefix` and constant values can be joined together. In the above example, `messageContext` matches either with `incontext` value or with `type_1`, `type_2`, `type_b`, `type_abc` ... etc.   
 The same **does not hold** for `anything-but` keyword, which cannot be mixed with exact values.

---

Apart from working with strings, filters can also operate on numerical values. This is done by using keyword numeric, as in the example below

```
functions:  
  hndl3:  
    handler: handler.fun3  
    events:  
      - sns:   
          arn: !Ref NotifyTopic  
          topicName: notifyTopic  
          filterPolicy:  
            messageType:  
              - hndl3  
            cost:  
              - numeric:   
                  - ">"  
                  - 0
```

Here, the message with attributes `messageType`equal to `hndl3` and cost greater than zero. The numeric filter accepts the following operators: `=`, `>`, `>=`,`<`, and `<=`. In addition, you can define a range of values. In the example below, the value of the cost attribute has to be in the range (0, 200) to be accepted.

```
cost:  
  - numeric:   
      - ">"  
      - 0  
      - "<"  
      - 200
```

You can even mix numeric and string attribute values, as in the example below

```
cost:  
  - unknown  
  - numeric:  
      - "="  
      - 100
```

where the `cost` attribute has to be either `100` or `unknown`.

---

SNS filtering can help you distribute the messages to the right consumers, reducing your computational cost on a little price of writing filters. It is a robust tool and can be used for all kind of receiver the SNS subscription can handle.

---

I hope you have enjoyed the story, and it could be helpful in your daily work. Feel free to contact me via [Twitter](https://twitter.com/MrTheodor) or [Linkedin](https://www.linkedin.com/in/jkrajniak/) if you have any questions or suggestions.

---

*Originally published at* [*https://dev.to*](https://dev.to/jkrajniak/efficient-message-broadcasting-with-sns-filtering-1c14) *on August 20, 2020.*