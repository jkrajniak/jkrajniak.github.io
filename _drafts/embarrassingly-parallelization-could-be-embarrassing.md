---
layout: post
title: "Embarrassingly parallelization could be embarrassing"
date: 2026-03-21
description: "In parallel computing, the term “embarrassingly parallel” refers to problems that are inherently easy to parallelize. These problems are…"
tags: []
---

---

### Embarrassingly parallelization could be embarrassing

In parallel computing, the term “embarrassingly parallel” refers to problems that are inherently easy to parallelize. These problems are characterized by a lack of dependencies between subtasks, allowing them to be executed simultaneously. For example, consider a situation where you have a set of URLs to fetch — these are completely independent jobs. The same could refer to analysing paths in the graphs. Here, the set of nodes and edges, that form graphs is constant. The input to the algorithm is a pair of nodes (source, target). In the next few paragraphs, I will show how using embarrassingly parallelization is not always a good idea.

### **Shortest Path Search on a Large Graph**

Let us consider the task of finding the shortest path between all pairs of nodes in a large graph with over 10.000 nodes. This problem represents a common scenario in various real-world applications, such as network routing, social network analysis, and analysing polymer networks.

I will focus on the last example — basically, we will examine a system of 10,000 molecules that form a high entanglement system. We treat each of the molecules as a node in our graph, and the chemical bonds between atoms that belong to different molecules, as edges in the graph. We are interested in finding the number of so-called dangling paths. These are characterized by the degree of the source/destination nodes — either source or destination need to have degree 2.

For a graph with n nodes, the total number of possible pairs of nodes is n\*(n-1)/2. In a complete graph with 10,000 nodes, this results in 49.5 million pairs of nodes. Finding the shortest path between each of these pairs is a computationally intensive task, especially for large graphs with complex structures.

#### Naive Implementation

Let’s first look into a naive implementation with two for-loops—one over the source nodes and the second over the target nodes.

```
import networkx as nx  
  
# Load the graph  
G = nx.read_edgelist('graph.edgelist')  
  
# Find the shortest path between all pairs of nodes  
results = []  
for source in G.nodes():  
    for target in G.nodes():  
        if source != target:  
            try:  
                results.append(nx.shortest_path(G, source, target))  
             except nx.NoShortestPath:  
                pass
```

#### Parallel Solution with Joblib

To improve performance, we can employ [joblib](https://joblib.readthedocs.io/en/stable/), a library that simplifies parallel processing in Python. Joblib provides a convenient interface for distributing tasks across multiple workers, enabling us to use multiple cores or processors.

```
import joblib  
import networkx as nx  
  
  
def find_shortest_path(G, source, target):  
    return nx.shortest_path(G, source, target)  
  
r = Parallel(n_jobs=-2, verbose=1)(delayed(find_shortest_path)(G, source, target)   
        for source in G.nodes() for target in G.nodes() if source != target)
```

So here, we pass the function that will be executed in parallel way, alongside with the parameters. One important note here, we have to pass the nx.Graph object to the function.

#### Multiprocessing Library with init\_worker Function

While joblib offers a straightforward parallelization approach, its internal mechanism of pickling and unpicking the graph structure can introduce significant overhead, especially for large graphs. To overcome this limitation, we can use the standard multiprocessing library along with the init\_worker function.

```
import multiprocessing  
import networkx as nx  
  
# Define a function to open the graph and find the shortest path between two nodes  
def init_worker():  
    global G  
    G = nx.read_edgelist('graph.edgelist')  
  
def find_shortest_path(source_target):  
    source, target = source_target  
    return nx.shortest_path(G, source, target)  
  
def main():  
    # Load the graph only once  
    G = nx.read_edgelist('graph.edgelist')  
    crosslink_matrix = [(i, j) for i in G.nodes() for j in G.nodes() if i > j]  
    # Create a parallel multiprocessing pool with init_worker function  
    pool = multiprocessing.Pool(initializer=init_worker)  
      
    # Submit tasks for each pair of nodes  
    results = pool.map(find_shortest_path, crosslink_matrix)
```

### Performance Comparison

Comparing the performance of the three implementations reveals a substantial difference. The naive implementation, without parallelization, exhibits the slowest execution time. The joblib-based parallel solution shows a moderate improvement but still suffers from the overhead of pickling and unpickling. The final solution, using the multiprocessing library and init\_worker function, demonstrates the most significant performance gain, achieving a substantial reduction in execution time.

### Further improvements

You can think about further improvements of the processing. For example, if your graph can be decomposed into disconnected subgraphs, then you can run this particular processing on the subgraphs. This make sense, as there is definitely no path between nodes that are in disconnected parts.

### Conclusion

Embarrassingly parallel problems, despite their inherent simplicity, can introduce performance bottlenecks if not addressed appropriately. By understanding the underlying mechanisms and employing appropriate parallelization techniques, we can significantly improve the efficiency of such problems. The case of shortest path search on a large graph illustrates the importance of careful implementation and the potential pitfalls of neglecting overhead factors.

**Additional Notes:**

- NetworkX is used in all three solutions to represent and manipulate the graph structure.
- The naive implementation suffers from the overhead of repeated graph loading for each pair of nodes.
- Joblib alleviates the repeated graph loading but incurs the overhead of pickling and unpickling the graph.
- The multiprocessing approach with init\_worker function eliminates the overhead of repeated graph loading and pickling, resulting in the most efficient solution.

---

I hope you have enjoyed the story, and it could be helpful in your daily work. Feel free to contact me via [X](https://twitter.com/MrTheodor) if you have any questions or suggestions.