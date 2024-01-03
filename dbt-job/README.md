# Vertica DBT cronjob on kubernetes

## Build image
```bash
docker build -t vertica-dbt .
```

## Test image

```bash
docker run \
--network=host \
--mount type=bind,source=/home/dbt_projects/vertica_upsert,target=/usr/app \
--mount type=bind,source=/root/.dbt/profiles.yml,target=/root/.dbt/profiles.yml \
dbt-vertica:latest \
ls
```

## Create k8s cronjob
### Update git sync variables
- GIT_SYNC_REPO
- GIT_SYNC_BRANCH 
- etc...

### Deploy cronjob
```bash
kubectl apply -f k8s-cronjob.yaml
```