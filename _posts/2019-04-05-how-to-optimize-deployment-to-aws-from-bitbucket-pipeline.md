---
layout: post
title: "How to optimize deployment to AWS from Bitbucket pipeline"
date: 2019-04-05
description: "A short story about how to update the deployment process to efficiently deploy the application from bitbucket pipelines to AWS"
tags:
  - aws
  - ci-cd
  - bitbucket-pipelines
  - devops
  - cloudformation
---

---

### How to optimize deployment to AWS using Bitbucket pipelines

![](https://cdn-images-1.medium.com/max/800/0*EDC2X0zN934fmRdv)

Photo by [Quinten de Graaf](https://unsplash.com/@quinten149?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

It is hard to imagine any serious software development work without continuous integration (CI) and continuous deployment (CD) steps. The first term describes the workflow, where developers integrated their changes frequently to a shared code repository. Each of the integration is preceded by a verification step, which is mostly a set of unit and end-to-end tests. Thanks to testing, at every development step we are assured that the changes in the code do not break the existing functionality (of course this is a very optimistic assumption and depends on the quality of tests). Moreover, frequent code integration reduces potential conflicts, which could happen if many developers modified a similar piece of code.

The continuous deployment process is closely related to continuous integration. Namely, after the changes pass tests in CI phase, the code can be automatically deployed to the production, staging, QA or whatever environment.

Despite the obvious benefits of having CI/CD, one potential pitfall could arise from the time needed to run the whole pipeline. The long-running CI process raises the temptation to skip the testing phase at all, which could lead to a degeneration of a codebase.

In this short story, I will share with you some tips that allow you to run more efficient the CI/CD within Bitbucket pipelines combined with deploying the code to Amazon Web Services (AWS).

### Do not stop the processing when there are no changes in your cloud formation template

Let's consider the following command that we used to deploy the cloud formation stack

```
aws cli --profile $(PROFILE) --region $(REGION) \  
    cloudformation deploy \  
    --stack-name stack \  
    --template-file ./cloud_formation/template.yaml
```

This will deploy a stack defined in **./cloud\_formation/template.yaml** file. However, if the file does not contain any changes to apply, the above command will fail with the error code 255 and the message:

```
No changes to deploy. Stack stack is up to date
```

In order to ignore this “error”, you can use option

```
--no-fail-on-empty-changeset
```

This makes sure that the result of the command will be 0 whenever no changes are required.

### Avoid unnecessary change in parameters passed to your cloud formation templates

In one of the projects that I worked, we noticed that a single deployment of cloud formation (CF) template costs around 200 seconds. This is a lot, respectively that during the deployment in the worst case scenario 22 different stacks had to be deployed. Therefore, we had to make sure that any changes to the parameters that we pass to the template are really necessary.

For the sake of exposition, let’s consider the following CF template that is responsible for creating the ECS task definition:

```
Parameters:  
  ImageName  
    Type: String
```

```
Resources:  
  Task:  
    Type: AWS::ECS::TaskDefinition  
    Properties:  
      Family: workers  
      TaskRoleArn: !Ref TaskRole  
      ContainerDefinitions:  
        - Name: "worker"  
          Memory: 128  
          Image: !Ref ImageName  
...
```

The **Image** specifies which image will be used to run the defined task. The best practice is to version your images with the tag. If your docker images are kept in [ECR](https://aws.amazon.com/ecr/) , the format of this name is `<aws-account-id>.dkr.ecr.<region>.amazonaws.com/<repository-name>:tag.`

Therefore, in order to update the code responsible for a given task, you have to push the new version of the image with the new tag to the repository. Next, you have to update CF stack with the **ImageName** that will include the new tag that points to the new version of the code.

For the CD, we have to automate the versioning of the docker images. One of the solutions is to use **git tag**, which can be obtained by running

```
git describe --tags --always
```

This will return either the current tag that points to the latest version, tag combined with the latest commit hash or commit hash. This is a pretty simple solution for the tagging but has one important drawback. Namely, in a case when your repository contains multiple separate modules (e.g. microservices) any commit to the repository will cause that all the docker containers will be rebuilt, even if only one module was touched.

A better approach is to calculate the hash of the code in the module that will be packaged into the docker image. This is especially simple if your code is compiled to single executable binary, like in Go. The hash can be calculated by

```
openssl dgst -r -sha256 ./bin/cmd-to-run | head -c 10
```

If your code base contains multiple files, you can very easily calculate a hash of the whole directory:

```
tar cf - directory-to-module | openssl dgst -r -sha256 | head -c 10
```

### Turn on caching for docker, pip, Go

Bitbucket allows you to enable caching for the docker containers as well as for the Python packages. This can be simply done by adding the following section

```
pipelines:  
  default:  
    - step:  
        name: Test  
        caches:  
          - docker  
          - pip  
          - golang
```

```
...  
definitions:  
  caches:  
    golang: $HOME/.cache/go-build
```

Although bitbucket does not have golang caching available, we can use [a custom definition](https://confluence.atlassian.com/bitbucket/caching-dependencies-895552876.html) set in the section **definitions.** By this, we can define the place where the cached objects are located.

### Parallelize fool!

[Bitbucket pipelines offer the ability to run the steps in parallel](https://confluence.atlassian.com/bitbucket/parallel-steps-946606807.html). This is pretty simple to set up. Below the example of the pipeline that contains several steps running in parallel and a pretty nice graphical representation of such config.

![](https://cdn-images-1.medium.com/max/800/1*wu_9ohdIQ6_nPEPR9o7JtQ.png)

```
pipelines:  
  default:  
    - parallel:  
      - step:  
        name: Test A  
        script: ./test_a.sh  
      - step:  
        name: Test B  
        script: ./test_b.sh  
      - step:  
        name: Test C  
        script: ./test_c.sh  
      - step:  
        name: Test D  
        script: ./test_d.sh  
    - step:  
      name: Deploy  
      script: ./deploy.sh
```

The parallel steps have some limitation. There is no support for nested parallel sections. Moreover, you cannot use the parallel steps to deploy your application. Therefore, this declaration below is not valid:

```
pipelines:  
  branches:  
    release:  
      - parallel:  
        - step:  
          name: Deploy service A  
          deployment: Production  
          script: ./deploy_A.sh  
        - step:  
          name: Deploy service B  
          deployment: Production  
          script: ./deploy_B.sh
```

Fortunately, we still can use an old good **make** instead of built-in bitbucket parallelization.

Let assume that we have a product composed of several services (A…F) that lays in one repository:

![](https://cdn-images-1.medium.com/max/800/1*X3T8fcOGwR9ZGxj4GUMQ3g.png)

The relationship between the services

```
.  
├─-Makefile  
├─-service_a  
|  ├─ ...  
|  └──Makefile  
├─-service_b  
|  ├─ ...  
|  └──Makefile  
├─-service_c  
|  ├─ ...  
|  └──Makefile  
├─-service_d  
|  ├─ ...  
|  └──Makefile  
├─-service_e  
|  ├─ ...  
|  └──Makefile  
└──-service_f  
   ├─ ...  
   └──Makefile
```

The build process of the whole product should take into account dependencies between services (as it is shown on the left diagram). Is there room here for parallel deployment? Apparently, yes, you can divide the process into three stages:

- service A, B, F
- service D
- service E and C

The root `Makefile` can be defined as follows

```
TARGETS=service_a service_b service_c service_d service_e service_f
```

```
.PHONY: $(TARGETS)
```

```
stage1: service_a service_b service_c  
»...echo stage_1
```

```
stage2: service_d  
»...echo stage_2
```

```
stage3: service_e service_f  
»...echo stage_3
```

```
deploy:  
»...$(MAKE)  stage1  
»...$(MAKE)  stage2  
»...$(MAKE)  stage3
```

```
$(TARGETS):  
»...$(MAKE) -C $@ deploy
```

Each of the individual services has own `Makefile` with the following definition:

```
deploy:  
»...sleep 10  
»...@echo Service A
```

The output is as expected:

```
$ make -s -j3 deploy  
Service A  
Service B  
Service C  
stage_1  
Service D  
stage_2  
Service E  
Service F  
stage_3
```

As we defined that every stage will cost us around 10s, we should expect that the total time will be 60 s; if we run it completely in parallel then the time should be reduced to 30se (stage 1 + stage 2 + stage 3).

![](https://cdn-images-1.medium.com/max/800/1*t8VC-kl7YLa-KjrbzsCV7w.png)

The results of running the pipeline with different values of **-jN**

The results for different values of `-jN` (running on the local machine)

- N=1: 60.1 s
- N=2: 40.0 s
- N=3: 30.0 s

Clearly, the parallel execution decreases the overall time needed for running `deploy` target. Obviously, there is no point in running with `-j` higher than `3` as only `stage 1` have three targets to run in parallel

### Conclusions

The bitbucket pipelines are a powerful tool that allows you integrating your deploying process very easily. A recent announcement of [bitbucket pipes](https://confluence.atlassian.com/bitbucket/pipes-958765631.html) provides seamless integration of your pipelines with many services.

---

At Nordcloud we are always looking for talented people. If you enjoy reading this post and would like to work with public cloud projects on a daily basis — check out our open positions [here](https://nordcloud.com/careers/).