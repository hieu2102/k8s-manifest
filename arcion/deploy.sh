#!/bin/bash

kubectl apply -f 1.ns.yaml
kubectl apply -f 2.ConfigMap.yaml
kubectl apply -f 3.license.yaml
kubectl apply -f 4.postgresql.yaml
kubectl apply -f 5.ntp.yaml
kubectl apply -f 6.Deployment.yaml
kubectl apply -f 7.Ingress.yaml
kubectl apply -f 8.StatefulSet.yaml
