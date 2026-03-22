---
layout: post
title: "Stream pub/sub messages to BigQuery with Dataflow"
date: 2026-03-21
description: "How to process a stream of incoming messages with additional message schema control, using Google Dataflow."
tags: []
---

---

### Stream pub/sub messages to BigQuery with Dataflow

#### How to process a stream of incoming messages with additional message schema control, using Google Dataflow.

In my last posts, I was focused on using Dataflow to move data from Datastore to BigQuery. In this post, I will show you how to implement a simple dataflow process, where incoming messages via pub/sub first are checked against predefined schemas and then stored in BigQuery.