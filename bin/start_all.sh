#!/bin/sh
# start_all.sh — 一键启动所有服务（ensure.sh 的简化版）
PEND="${PEND:-/home/user/.dsh_pend}"
exec sh "$PEND/bin/ensure.sh"
