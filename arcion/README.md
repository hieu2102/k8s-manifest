# Arcion K8S Deployment

## Create namespace
```bash
kubectl apply -f ns.yaml
```

## Create database
```bash
kubectl apply -f postgresql.yaml
```

## Create license secret
```bash
kubectl apply -f license.yaml
```

## Deploy Arcion
```bash 
kubectl apply -f arcion.yaml
```