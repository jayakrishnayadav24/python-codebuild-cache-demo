# Speed Up Python Builds in AWS CodePipeline Using CodeBuild pip Cache

## The Problem: pip Downloads Everything on Every Build

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

A real production Python app with ML libraries, AWS SDK, FastAPI, databases, Kafka, and observability tools can easily have **80–100 packages** with a total download size of **2–4 GB**. On a fresh CodeBuild container (ephemeral — destroyed after every build), this happens from scratch every time.

The fix: **cache the pip download cache between builds using CodeBuild's S3 cache**.

---

## What Gets Cached

pip stores downloaded wheel files and package metadata in `~/.cache/pip`. On a warm cache hit, pip skips the download entirely and installs directly from the local cache.

By pointing CodeBuild's cache at `/root/.cache/pip/**/*`:
1. **First build** — pip downloads everything, cache is saved to S3
2. **Every build after** — cache is restored from S3, pip installs from local wheels

---

## Project Setup: A Heavy Python Project

This is a real-world production Python app using:

- **Web**: FastAPI, Uvicorn, Gunicorn, Flask, Django, HTTPX, aiohttp
- **Databases**: SQLAlchemy, Alembic, psycopg2, asyncpg, Motor, PyMongo, Redis, Elasticsearch, Cassandra
- **AWS**: boto3, botocore, aiobotocore, aws-lambda-powertools, aws-cdk-lib
- **ML / Data Science**: TensorFlow, PyTorch, torchvision, Transformers, scikit-learn, XGBoost, LightGBM, CatBoost, NumPy, Pandas, SciPy, OpenCV
- **Data Processing**: Apache Airflow, Celery, Kafka, PySpark, Dask, Ray, PyArrow
- **API / Serialization**: Pydantic, gRPC, Protobuf, GraphQL, Marshmallow
- **Auth / Security**: python-jose, passlib, cryptography, PyJWT, Authlib
- **Observability**: Prometheus, OpenTelemetry, Sentry, Datadog, structlog
- **Testing**: pytest, moto, factory-boy, Faker, localstack-client

Without caching, `pip install -r requirements.txt` on this project downloads **2–4 GB** on every build.

---

## The buildspec.yml — The Key Part

```yaml
version: 0.2

phases:
  install:
    runtime-versions:
      python: 3.11
    commands:
      - pip install --upgrade pip
      - pip install -r requirements.txt
  pre_build:
    commands:
      - python --version
  build:
    commands:
      - pytest tests/ --tb=short || true
  post_build:
    commands:
      - echo "Build completed on `date`"

artifacts:
  files:
    - '**/*'

cache:
  paths:
    - '/root/.cache/pip/**/*'    # <-- This is the magic line
```

The difference from Maven: pip's cache is at `/root/.cache/pip`, not `~/.m2`. Everything else works identically.

---

## Configuring the Cache in CodeBuild / CloudFormation

The full `pipeline.yml` CloudFormation template provisions:
- S3 bucket for build artifacts (30-day lifecycle)
- S3 bucket for pip cache (30-day lifecycle)
- IAM roles for CodeBuild and CodePipeline
- CodeBuild project with S3 cache at `pip-cache/production-app`
- CodePipeline with GitHub source via CodeStar Connection

Key section in the CodeBuild project:

```yaml
Cache:
  Type: S3
  Location: !Sub "python-demo-cache-${AWS::AccountId}/pip-cache/production-app"
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

## How the Cache Flow Works

```
Git push to main
       │
       ▼
CodePipeline triggers
       │
       ▼
CodeBuild starts
       │
       ▼
Restore cache from S3
/root/.cache/pip ← s3://python-demo-cache-<account>/pip-cache/production-app
       │
       ▼
pip install -r requirements.txt
(installs from local wheels, skips downloads)
       │
       ▼
Run tests
       │
       ▼
Save updated cache back to S3
       │
       ▼
Upload artifact to S3
```

---

## Real Build Time Comparison

| Scenario | pip Download Time | Total Build Time |
|---|---|---|
| No cache (cold start) | ~10–15 minutes | ~15–20 minutes |
| With S3 cache (warm) | ~20–40 seconds | ~2–4 minutes |
| Savings | **~12 minutes per build** | **~75–80% faster** |

Python builds save even more time than Java/Maven because ML libraries like TensorFlow and PyTorch are massive (500–800 MB each).

---

## Maven vs pip Cache: Key Differences

| | Maven (Java) | pip (Python) |
|---|---|---|
| Cache path | `/root/.m2/**/*` | `/root/.cache/pip/**/*` |
| Typical cold download | ~500 MB – 1.5 GB | ~2–4 GB |
| Warm build savings | ~60–70% | ~75–80% |
| Cache invalidation | Delete S3 prefix | Delete S3 prefix |

---

## Cache Invalidation

pip's cache is additive just like Maven's. To force a clean download:

```bash
aws s3 rm s3://python-demo-cache-<account-id>/pip-cache/production-app --recursive
```

The next build does a full cold download and repopulates the cache.

---

## Pro Tips

**1. Pin all versions in requirements.txt**
Unpinned versions cause cache misses because pip re-resolves dependencies every time.

**2. Use `--no-deps` for known-stable packages**
For packages you know won't change, `pip install --no-deps` skips dependency resolution entirely.

**3. Split requirements files**
```
requirements-base.txt    ← stable heavy deps (torch, tensorflow) — rarely changes
requirements.txt         ← app deps — changes frequently
```
Cache `requirements-base.txt` installs separately so a change in app deps doesn't invalidate the heavy ML library cache.

**4. Use `BUILD_GENERAL1_LARGE` for ML projects**
TensorFlow and PyTorch need more memory during installation. `LARGE` compute (7 GB RAM) prevents OOM kills during pip install.

---

## Summary

| What | How |
|---|---|
| What to cache | `/root/.cache/pip/**/*` |
| Cache type | Amazon S3 |
| Where to configure | `buildspec.yml` → `cache.paths` + CodeBuild project cache settings |
| Time saved | 75–80% faster builds on warm cache |
| Cache invalidation | Delete S3 prefix manually |

For Python projects with ML dependencies, this is the single highest-impact CI/CD optimization you can make. TensorFlow and PyTorch alone are over 1 GB — downloading them on every build is pure waste.
