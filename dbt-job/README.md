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
*Notes*: files' names for `from-file` args must match the example

### Create git-sync credentials
Generate SSH key
```bash
ssh-keygen -t rsa -b 4096 -f ssh
```

Create `kubernetes secret`

```bash
kubectl create secret generic git-creds --from-file=./ssh -n dbt
```

### Create dbt's `profile.yml` `configmap`

```bash
kubectl create configmap dbt-profiles --from-file=./profiles.yml -n dbt
```
### Update git sync variables
- GIT_SYNC_REPO
- GIT_SYNC_BRANCH 
- etc...

### Deploy cronjob
```bash
kubectl apply -f k8s-cronjob.yaml
```