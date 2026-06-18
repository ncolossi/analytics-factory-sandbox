#!/usr/bin/env bash
# Caso ruim: cópia de dados fora do Dataform.
bq cp project:bronze_erp.orders project:silver_sales.orders
