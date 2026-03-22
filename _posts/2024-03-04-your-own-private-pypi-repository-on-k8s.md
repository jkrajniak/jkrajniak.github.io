---
layout: post
title: "Your own private PyPi repository on K8s"
date: 2024-03-04
description: "Imagine your ML team struggling with a sprawling Python codebase — snippets, internal libraries, notebooks, and even production code in…"
tags:
  - kubernetes
  - python
  - pypi
  - docker
  - devops
---

---

![](https://cdn-images-1.medium.com/max/800/0*JrbEFKkNsKgW_B4U)

Photo by [Growtika](https://unsplash.com/@growtika?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

### Your Own Private PyPi Repository on K8s

Imagine your ML team struggling with a large Python codebase — snippets, internal libraries, notebooks, and even production code in Kubernetes. All these are dispersed around several GitHub repositories. The usual approach is to copy-paste appropriate snippets or even entire parts of libraries.

In this post, I will demonstrate how to set up a private PyPI repository within your Kubernetes cluster, offering a simple yet powerful solution for managing and deploying your internal Python packages.

---

Before we get into the practical steps, let’s first focus on how the inner Python package repositories work. This will help us understand the ingredients of the setup.

#### **PEP 503: The Orchestrator of Package Discovery**

[PEP 503](https://peps.python.org/pep-0503/) is the blueprint for package repositories in Python. It defines a standardized interface, ensuring tools like pip know exactly where to search for specific package versions.

Interestingly, the core of a package simple repository’s index lies in an HTML5 page. This page lists all available projects, each linked to its specific versions. While manually creating these HTML files is technically possible, it’s not an efficient or error-free approach.

#### simple503: Automation for Effortless Index Generation

This is where [simple503](https://simple503.readthedocs.io/en/latest/) comes. It automates the generation of PEP 503-compliant index files, saving us valuable time and potential errors. This allows us to focus on the more exciting aspects of setting up our private PyPI repository within the Kubernetes cluster.

With the fundamental concepts clear, let’s start with the architecture overview.

![](https://cdn-images-1.medium.com/max/800/1*-OmfCW_TQZCOkk5JeDYiZw.png)

Sketch of the solution (by author)

### Let’s start

#### Components

As you see in the above picture, the solution consists of a few components:

1. Bucket with the wheel files
2. K8s service
3. Ingress with basic auth
4. Github workflow to orchestrate it

### Workflow

The workflow is straightforward. We use Github workflow to build the wheel package. Next, the package is uploaded to the bucket, and afterwards, we restart the deployment to update the wheels on the ephemeral storage and refresh the index page.

### Basic auth

As we want to have a private PyPi server, we need some security. The simplest way is to use the basic auth approach available out-of-box in the nginx ingress controller.

The username and password will be stored in K8s secret, which is defined in the Terraform block

```
resource kubernetes_secret "pypi_auth_secrets" {  
  metadata {  
      name = "pypi-basic-auth"  
  }  
  data = {  
    auth = "user1:${bcrypt(var.pypi_password)}"  
  }  
}
```

The password is passed via the Terraform input variables. The important thing is that you should use something other than the [basic auth secret type.](https://kubernetes.io/docs/concepts/configuration/secret/#basic-authentication-secret) Instead, use a simply [opaque type](https://kubernetes.io/docs/concepts/configuration/secret/#opaque-secrets) with the field **auth,** encrypted with a bcrypt.

### Kubernetes service

The simple 503 index is nothing more than a static HTML file. Hence, we can use nginx server to show that page. Let’s start with basic Dockerfile:

```
FROM python:3.11.1-slim-bullseye  
  
RUN apt-get update && apt-get install -y \  
    python3 \  
    python3-pip \  
    python3-setuptools \  
    python3-wheel \  
    python3-venv \  
    nginx \  
    curl  
  
RUN pip3 install simple503  
  
RUN mkdir -p /www/html && chmod 777 /www/html  
  
COPY simple503.toml .  
COPY nginx.conf /etc/nginx/  
COPY entrypoint.sh /usr/local/bin/  
COPY sync_bucket.sh /usr/local/bin/  
  
# Expose HTTP  
EXPOSE 8080
```

The `entrypoint.sh` is responsible for generating the index, based on the files that are copied by `sync_bucket.sh` and then starting the nginx server

```
#!/bin/bash  
  
simple503 /www/html && echo "simple503 success" || echo "simple503 failed"  
  
echo "nginx start"  
/usr/sbin/nginx
```

For your customized environment, you have to change `sync_bucket.sh` — the script to work in your cloud environment.

Next, we need a K8s deployment with the service.

```
apiVersion: apps/v1  
kind: Deployment  
metadata:  
  name: pypi-server  
spec:  
  selector:  
    matchLabels:  
      app: pypi-server  
  template:  
    metadata:  
      labels:  
        app: pypi-server  
    spec:  
      containers:  
        - image: pypi-simple503:latest  
          imagePullPolicy: Always  
          name: pypi-simple503  
          command: ["entrypoint.sh"]  
          ports:  
            - containerPort: 8080  
              protocol: TCP  
          volumeMounts:  
            - name: pypi-server-volume  
              mountPath: /www/html  
          resources:  
            requests:  
              cpu: "100m"  
              memory: "50Mi"  
            limits:  
              cpu: "250m"  
              memory: "100Mi"  
      initContainers:  
        - name: pypi-server-init  
          image: pypi-simple503  
          imagePullPolicy: Always  
          command: ["sync_bucket.sh"]  
          volumeMounts:  
            - name: pypi-server-volume  
              mountPath: /www/html  
      volumes:  
        - name: pypi-server-volume  
          emptyDir:  
            sizeLimit: 1Gi  
---  
apiVersion: v1  
kind: Service  
metadata:  
  name: pypi-server-svc  
spec:  
  selector:  
    app: pypi-server  
  ports:  
    - protocol: TCP  
      port: 8080  
      targetPort: 8080
```

### Ingress with basic auth

With the service, we can now configure Ingress which will be a gateway to our service.

```
apiVersion: networking.k8s.io/v1  
kind: Ingress  
metadata:  
  name: ingress-pypi  
  annotations:  
    nginx.ingress.kubernetes.io/auth-type: basic  
    nginx.ingress.kubernetes.io/auth-secret: pypi-basic-auth  
    nginx.ingress.kubernetes.io/auth-realm: 'Authentication Required'  
  namespace: default  
spec:  
  ingressClassName: nginx  
  rules:  
  - host: py.example.io  
    http:  
      paths:  
      - path: /  
        pathType: Prefix  
        backend:  
          service:  
            name: pypi-server-svc  
            port:  
              number: 8080
```

Here, we define that the [ingress](https://github.com/kubernetes/ingress-nginx) will perform basic auth, with the secrets stored in *pypi-basic-auth.* Internally, the ingress is using the nginx server to perform all of these auth processes.

### Build Docker image with private PyPi

We successfully created a private PyPi repository, and now we can install packages from it, just by using `--extra-index-url`

```
pip3 install --extra-index-url https://username:password@py.example.io my-package
```

But how do you do it inside your Dockerfile? The easiest way will be to pass the credentials directly to the files — easiest but insecure. Fortunately, we have another option — [secret mounts](https://docs.docker.com/build/building/secrets/).

Below is an example of a Dockerfile that uses our PyPi server

```
FROM ubuntu:latest  
  
ENV PIP_EXTRA_INDEX_URL=https://py.example.io  
RUN --mount=type=secret,id=netrc,dst=/root/.netrc pip install private_package
```

You can immediately spot extra parameters in the **RUN** command. The option `mount` of type *secret* will mount the content of the file from the host machine (netrc) securely inside the layer of the container on path /root/.netrc. The definition of the file is set in the `docker build` command:

```
docker build --secret id=netrc,src=source_netrc -t example-container .
```

The mount is secure in the sense, that the content of the fill won’t be available during the execution of the container, and also won’t be stored inside the layer.

The [.netrc](https://www.gnu.org/software/inetutils/manual/html_node/The-_002enetrc-file.html) file is defined by:

```
machine py.example.io  
  login user  
  password pass
```

### Conclusions

By establishing your own private PyPI server within a Kubernetes cluster, you create a centralized and secure platform for managing internal Python packages for your team.

I hope you have enjoyed the story, and it could be helpful in your daily work. Feel free to contact me via [Twitter](https://twitter.com/MrTheodor), if you have any questions or suggestions. You can also support me by [buying me a coffee](https://buymeacoffee.com/jkrajniak).

### Stackademic 🎓

Thank you for reading until the end. Before you go:

- Please consider **clapping** and **following** the writer! 👏
- Follow us [**X**](https://twitter.com/stackademichq) **|** [**LinkedIn**](https://www.linkedin.com/company/stackademic) **|** [**YouTube**](https://www.youtube.com/c/stackademic) **|** [**Discord**](https://discord.gg/in-plain-english-709094664682340443)
- Visit our other platforms: [**In Plain English**](https://plainenglish.io) **|** [**CoFeed**](https://cofeed.app/) **|** [**Venture**](https://venturemagazine.net/) **|** [**Cubed**](https://blog.cubed.run)
- More content at [**Stackademic.com**](https://stackademic.com)