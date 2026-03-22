---
layout: post
title: "Control your Airflow DAG from an external database"
date: 2022-05-02
description: "Apache Airflow is a very popular framework for scheduling, running and monitoring tasks, which are grouped into DAG (direct-acyclic…"
tags:
  - airflow
  - python
  - data-engineering
  - workflow-orchestration
---

---

![](https://cdn-images-1.medium.com/max/800/1*bfWlGk1As43U9r_tV_CdQA.jpeg)

Zaanse Schans, Zaandam, Netherlands (by author)

### Control your Airflow DAGs from an external database

Apache Airflow is a very popular framework for scheduling, running and monitoring tasks, which are grouped into DAG (directed-acyclic graph). Each DAG has several parameters that describe how and when DAG will be executed. DAG itself is composed of tasks arranged in a flow. The DAG parameters are defined as the properties of the [DAG class](https://github.com/apache/airflow/blob/main/airflow/models/dag.py#L184) and stored in the code. This solution is sufficient in many cases.

However, the configuration of DAGs can be delegated and stored elsewhere — in some database that is linked with GUI for external users.

By this, some parameters of DAGs could be defined without touching the code source, e.g. by non-developers. For example, imagine a chemistry laboratory where the automated processes are controlled by Airflow, and chemists could change some parameters using a web interface.

---

In this short story, I will show how to use an external configuration source to dynamically create and configure DAGs. One assumption that is made here, all DAGs are similar in terms of tasks and relationships. Therefore, only a few parameters are configurable via the database:

- scheduling time
- execution parameters

![](https://cdn-images-1.medium.com/max/800/1*M-yvjMW48kSoVpKOx6abmw.png)

The flow of dynamically configured DAGs (by author)

The solution is composed of two DAGs:

- **read\_config** which is responsible for fetching the configuration from database
- **dynamic\_dags** that is responsible for creating DAGs, based on the configuration

### Read configuration

One could ask why we need two DAGs, and why not have everything in one DAG. This is because of how Airflow is processing Python files. Every nth seconds the scheduler scans files in `dags/` folder and evaluates them using a Python interpreter. The scanning frequency is controlled by `dag_dir_list_interval` parameter.   
Therefore, during the evaluation part, we shouldn’t do any expensive actions — obviously connecting to a database and reading tables are one of them.

Instead, the database reading part should be moved to the code that is run by an operator (like [PythonOperator](https://airflow.apache.org/docs/apache-airflow/stable/howto/operator/python.html)). And this is exactly what is happening in `read_config` DAG.

Inside the DAG there is a single task run by [PythonOperator](https://airflow.apache.org/docs/apache-airflow/stable/howto/operator/python.html) which does

- Read a configuration from database (i.e. `config.dags`)
- Put the configuration into the Airflow variable

That’s it. The Airflow variable storage is used to keep the configuration (using JSON format). Below is the DAG definition:

```
import logging  
from datetime import timedelta  
  
import airflow  
import mysql.connector  
from airflow import DAG  
from airflow.models.connection import Connection  
from airflow.models.variable import Variable  
from airflow.operators.python import PythonOperator  
  
logger = logging.getLogger("airflow.task")  
  
default_args = {  
    "owner": "airflow",  
    "depends_on_past": False,  
    "retries": 0,  
    "retry_delay": timedelta(minutes=5),  
}  
  
mysql_connection = Connection.get_connection_from_secrets("mysql")  
  
  
def read_dags_config():  
    db_conn = mysql.connector.connect(host=mysql_connection.host, user=mysql_connection.login,  
                                      password=mysql_connection.password, database='config')  
    cursor = db_conn.cursor()  
    cursor.execute("select id, enabled, schedule, description from config.dags")  
  
    rows = cursor.fetchall()  
  
    if rows is None:  
        rows = []  
  
    logger.info(f"Config rows: {rows}")  
    if len(rows) > 0:  
        Variable.set("dags_config", rows, serialize_json=True)  
  
  
with DAG(  
        "read_config",  
        default_args=default_args,  
        schedule_interval="@hourly",  
        start_date=airflow.utils.dates.days_ago(0),  
        catchup=False) as dag:  
    PythonOperator(task_id="read-config", python_callable=read_dags_config, dag=dag)
```

The configuration from a database is ready every hour. The rows are serialized to JSON and saved in Airflow Variable:

![](https://cdn-images-1.medium.com/max/800/1*AHvtV5CHtR76-90M9hi0-Q.png)

List of variables in Airflow (by author)

### Dynamic DAG

The second dag — Dynamic DAG — is responsible for creating DAGs. The solution uses the way how Airflow is processing Python files. Basically, during the scanning of files in `dags/` Airflow is looking for objects that are of type [DAG](https://github.com/apache/airflow/blob/main/airflow/models/dag.py#L185). Internally this is The py file is evaluated by Python interpreter and then the `globals()` dictionary is scanned.

The procedure is straightforward. First, we get the configuration from the variable with the list of DAGs to create. Next, we iterate over that list and run the function that returns `DAG` object. And that `DAG` object we place as a variable in global() dictionary.

```
from datetime import timedelta  
  
import airflow  
from airflow import DAG  
from airflow.models.variable import Variable  
from airflow.operators.python import PythonOperator  
  
default_args = {  
    "owner": "airflow",  
    "depends_on_past": False,  
    "start_date": airflow.utils.dates.days_ago(0),  
    "retries": 2,  
    "retry_delay": timedelta(minutes=5),  
}  
  
  
def create_dag(dag_id: str, schedule: str = None, description: str = None):  
    dag = DAG(  
        dag_id,  
        default_args=default_args,  
        schedule_interval=schedule,  
        dagrun_timeout=timedelta(hours=1),  
        catchup=False,  
        description=description)  
  
    task_1 = PythonOperator(task_id="task_1", python_callable=lambda: x+1, dag=dag)  
    task_2 = PythonOperator(task_id="task_2", python_callable=lambda: 1, dag=dag)  
  
    task_1 >> task_2  
  
    return dag  
  
  
dags_config = Variable.get("dags_config", deserialize_json=True)  
  
for dag_id, schedule, description in dags_config:  
    globals()[f"dag-{dag_id}"] = create_dag(f"dag-{dag_id}", schedule, description)
```

Here, two important parts should be highlighted. A function `create_dag` is responsible for the whole process of defining tasks and relationships between them. And, the last part, iterates over the configurations from DB. Notice the usage of `globals()` the built-in method, which returns a dictionary.

![](https://cdn-images-1.medium.com/max/800/1*6w8QmldDZpLp4Pd4Nh_BxA.png)

List of created dynamically DAGs (by author)

---

To sum up, Airflow is still nothing more than a regular Python code. Therefore, nothing stands in the way to use all features of language and ecosystem.

---

I hope you have enjoyed the story, and it could be helpful in your daily work. Feel free to contact me via [Twitter](https://twitter.com/MrTheodor), if you have any questions or suggestions. You can also support me by [buying me a coffee](https://buymeacoffee.com/jkrajniak).