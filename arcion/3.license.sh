#!/bin/bash
kubectl -n arcion delete configmap arcion-license

kubectl -n arcion create configmap arcion-license --from-file ./replicant.lic