# Arcion K8S Deployment
*TL/DR*: use deployment script (`deploy.sh`) and configure `license.yaml` ConfigMap
```yaml
---
apiVersion: v1
kind: ConfigMap
metadata:
  namespace: arcion
  name: arcion-license
data:
  replicant.lic: |
    {
    "license": { "your actual license data"}
    }

```


## Dependencies
- local NTP server
got the following error when using default NTP (`time.google.com`) 

```plaintext
ntplib.NTPException: No response received from time.google.com.
```

- postgresql
repository database



## Create namespace
```bash
kubectl apply -f ns.yaml
```
## Create ConfigMap
```bash
kubectl apply -f ConfigMap.yaml
```

## Create Dependencies
```bash
kubectl apply -f postgresql.yaml
kubectl apply -f ntp.yaml
```

## Create license secret
```bash
kubectl apply -f license.yaml
```

## Deploy Arcion
```bash 
kubectl apply -f arcion.yaml
```