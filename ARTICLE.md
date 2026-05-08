# Speed Up Python Builds in AWS CodePipeline Using CodeBuild Caching

## The Problem: pip Installs Everything on Every Build

If you've run a production Python application through AWS CodePipeline, you've seen this on every single build:

```
Collecting tensorflow==2.16.1
  Downloading tensorflow-2.16.1-cp311-cp311-linux_x86_64.whl (589 MB)
Collecting torch==2.3.0
  Downloading torch-2.3.0-cp311-cp311-linux_x86_64.whl (779 MB)
Collecting pyspark==3.5.1
  Downloading pyspark-3.5.1.tar.gz (317 MB)
...
```

A real production Python app with ML libraries, AWS SDK, FastAPI, databases, Kafka, and observability tools can easily have **80–100 packages** with a total size of **2–4 GB**. On a fresh CodeBuild container (ephemeral — destroyed after every build), this happens from scratch every time.

There are **3 ways** to fix this, each with different tradeoffs. Let's go through all of them.

---

## Approach 1: pip Wheel Cache (`/root/.cache/pip`)

### How it works

pip stores downloaded wheel files in `/root/.cache/pip`. By caching this directory in S3, the next build skips downloading but still runs `pip install` to extract and install the wheels.

```yaml
cache:
  paths:
    - '/root/.cache/pip/**/*'
```

### What it saves

- ✅ Skips downloading packages from PyPI
- ❌ Still runs `pip install` on every build (extracts wheels, resolves deps)
- ❌ Large ML wheels (torch=779MB, tensorflow=589MB) make the S3 cache itself huge — unarchiving can take as long as downloading

### Build time comparison

| Scenario | Build Time |
|---|---|
| No cache | ~15–20 min |
| pip wheel cache (warm) | ~8–12 min |
| Savings | ~30–40% |

### When to use

Good for projects with small-to-medium dependencies. Not ideal for ML-heavy projects where wheel files are hundreds of MB each.

---

## Approach 2: Virtualenv Cache with Hash Invalidation (`/root/venv`)

### How it works

Instead of caching downloaded wheels, cache the **fully installed virtualenv**. On a cache hit, skip `pip install` entirely — just use the restored venv directly.

The key addition is a **hash check**: compute an MD5 of your `requirements.txt` files and store it in the venv. If the hash matches on the next build, the requirements haven't changed — use the cache. If the hash differs, rebuild the venv from scratch.

```yaml
cache:
  paths:
    - '/root/venv/**/*'
```

### The buildspec.yml

```yaml
version: 0.2

phases:
  install:
    runtime-versions:
      python: 3.11
    commands:
      - REQUIREMENTS_HASH=$(md5sum requirements.txt requirements-heavy.txt | md5sum | cut -d' ' -f1)
      - echo "Requirements hash $REQUIREMENTS_HASH"
      - |
        if [ -d "/root/venv" ] && [ -f "/root/venv/.hash" ] && [ "$(cat /root/venv/.hash)" = "$REQUIREMENTS_HASH" ]; then
          echo "Cache HIT - virtualenv is valid, skipping install"
        else
          echo "Cache MISS - requirements changed or first build, installing..."
          rm -rf /root/venv
          python -m venv /root/venv
          /root/venv/bin/pip install --upgrade pip
          /root/venv/bin/pip install -r requirements-heavy.txt
          /root/venv/bin/pip install -r requirements.txt
          echo "$REQUIREMENTS_HASH" > /root/venv/.hash
        fi
  pre_build:
    commands:
      - /root/venv/bin/python --version
      - /root/venv/bin/pip list | wc -l
  build:
    commands:
      - /root/venv/bin/pytest tests/ --tb=short || true
  post_build:
    commands:
      - echo "Build completed on `date`"

artifacts:
  files:
    - '**/*'

cache:
  paths:
    - '/root/venv/**/*'
```

### What it saves

- ✅ Skips `pip install` entirely on cache hit
- ✅ Hash check auto-invalidates when requirements change
- ✅ Fastest warm build time
- ⚠️ Venv contains absolute paths — if CodeBuild changes the Python version or container, venv may break
- ⚠️ Full venv can be 2–3 GB in S3

### Build time comparison

| Scenario | Build Time |
|---|---|
| No cache (cold) | ~15–20 min |
| venv cache (warm, no requirements change) | ~1–2 min |
| venv cache (warm, requirements changed) | ~15–20 min (rebuilds) |
| Savings on warm hit | **~85–90%** |

### When to use

Best for teams where requirements change infrequently (e.g., stable ML projects). The hash check ensures correctness — if you add a new package, the next build automatically detects the change and rebuilds the venv.

---

## Approach 3: Custom Docker Image in ECR (Production Best Practice)

### How it works

Build a custom Docker image with all heavy dependencies pre-installed, push it to Amazon ECR, and configure CodeBuild to use that image. Zero install time on every build.

```dockerfile
FROM public.ecr.aws/amazonlinux/amazonlinux:2023

RUN pip install tensorflow torch torchvision pyspark \
    xgboost lightgbm scikit-learn pandas numpy \
    fastapi uvicorn sqlalchemy boto3 celery kafka-python \
    # ... all your deps
```

```yaml
# In CodeBuild project
Environment:
  Type: LINUX_CONTAINER
  Image: <account>.dkr.ecr.us-east-1.amazonaws.com/python-build:latest
```

### What it saves

- ✅ Zero install time — packages already in the image
- ✅ Fully reproducible — same image = same environment
- ✅ No cache invalidation issues
- ❌ Need to rebuild and push the Docker image when dependencies change
- ❌ Adds complexity (ECR repo, image build pipeline)

### When to use

Production teams with stable, large dependency trees. The overhead of maintaining a custom image pays off when you have 50+ builds per day.

---

## Comparison: All 3 Approaches

| | pip Wheel Cache | venv Cache | Custom Docker (ECR) |
|---|---|---|---|
| Cold build | ~15–20 min | ~15–20 min | ~1–2 min (always) |
| Warm build | ~8–12 min | ~1–2 min | ~1–2 min |
| Auto-invalidation | ✅ (additive) | ✅ (hash check) | ❌ (manual rebuild) |
| Complexity | Low | Medium | High |
| Best for | Small/medium deps | ML projects, stable deps | Large teams, many builds |

---

## Project Setup: A Heavy Python Project

This demo uses a real-world production Python app with:

- **Web**: FastAPI, Uvicorn, Gunicorn, HTTPX, aiohttp
- **Databases**: SQLAlchemy, Alembic, psycopg2, asyncpg, Motor, PyMongo, Redis, Elasticsearch, Cassandra
- **AWS**: boto3, aiobotocore, aws-lambda-powertools, aws-cdk-lib
- **ML / Data Science**: TensorFlow, PyTorch, Transformers, scikit-learn, XGBoost, LightGBM, CatBoost, NumPy, Pandas, OpenCV
- **Data Processing**: Celery, Kafka, PySpark, Dask, PyArrow
- **API / Serialization**: Pydantic, gRPC, GraphQL, Marshmallow
- **Auth / Security**: python-jose, passlib, PyJWT, Authlib
- **Observability**: Prometheus, OpenTelemetry, Sentry, Datadog, structlog
- **Testing**: pytest, moto, factory-boy, Faker, localstack-client

---

## Configuring the Cache in CloudFormation

The `pipeline.yml` template provisions everything — S3 buckets, IAM roles, CodeBuild with cache, and CodePipeline connected to GitHub.

Key section for venv cache:

```yaml
CodeBuildProject:
  Type: AWS::CodeBuild::Project
  Properties:
    Cache:
      Type: S3
      Location: !Sub "python-demo-cache-${AWS::AccountId}/venv-cache/production-app"
```

---

## Deploying the Stack

**Deploy:**
```bash
aws cloudformation deploy \
  --template-file pipeline.yml \
  --stack-name python-codebuild-cache-demo \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

**Check status:**
```bash
aws cloudformation describe-stacks \
  --stack-name python-codebuild-cache-demo \
  --region us-east-1 \
  --query "Stacks[0].StackStatus"
```

**Delete when done:**
```bash
aws cloudformation delete-stack \
  --stack-name python-codebuild-cache-demo \
  --region us-east-1
```

---

## Cache Invalidation

**venv cache** — automatic via hash check. If `requirements.txt` changes, the next build detects it and rebuilds:
```
Requirements hash abc123 != def456 → Cache MISS → rebuilding venv
```

**Manual invalidation** (force full rebuild):
```bash
aws s3 rm s3://python-demo-cache-<account-id>/venv-cache/production-app --recursive
```

---

## Summary

For Python projects in AWS CodePipeline, use the approach that matches your team:

- **Getting started** → pip wheel cache (`/root/.cache/pip`) — 3 lines in buildspec
- **ML/heavy projects** → venv cache with hash check — best balance of speed and correctness
- **Large teams, many builds** → Custom Docker image in ECR — zero install time always

The venv cache with hash invalidation is the sweet spot for most production Python projects. It gives you near-zero install time on warm builds while automatically handling requirements changes correctly.
