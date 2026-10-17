# Docker services

Lessons declare the services they need: `services: [postgres]` on the lesson node in `curriculum.yaml`. `codelabgen scaffold course` writes `docker-compose.yml` with exactly those services. `codelabgen verify` and `./run.sh` start them with `docker compose up -d --wait <services>`.

## Built in

| Name | Image | Variable (default in `.env.example`) |
|---|---|---|
| `postgres` | `postgres:17`, user/password/db `codelab` | `POSTGRES_URL=postgresql://codelab:codelab@localhost:5432/codelab` |
| `redis` | `redis:8` | `REDIS_URL=redis://localhost:6379/0` |

## Custom services: `.codelabgen/services.yaml`

For anything else, define the Compose service and the variables lessons use to reach it:

```yaml
qdrant:
  definition:                       # a Docker Compose service, as is
    image: qdrant/qdrant:v1.15.4     # pin a version
    ports: ["6333:6333"]
    volumes: ["qdrant-data:/qdrant/storage"]
    healthcheck:                     # required in practice: `up --wait` waits for healthy
      test: ["CMD-SHELL", "bash -c ':> /dev/tcp/127.0.0.1/6333' || exit 1"]
      interval: 2s
      timeout: 3s
      retries: 30
  env:
    - name: QDRANT_URL
      description: URL of the course Qdrant (docker compose service)
      default: http://localhost:6333
```

Rules:
- **Pin the image tag.** Never `latest`.
- **Always give a healthcheck,** using a tool the image actually contains (many minimal images have no `curl`). Check the image's docs.
- **Use named volumes** (they are declared automatically) so data survives restarts.
- **Use standard ports.** Lessons connect through the variable, never a hardcoded host or port.
- **Variables:** a non-secret default URL, so `.env` works out of the box.
- **Run `codelabgen curriculum validate`** afterwards; it checks that every service a lesson names is defined.
