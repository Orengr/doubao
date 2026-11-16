#!/bin/bash
# test_nginx_runtime.sh — 真实 nginx 运行态验证
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  PASS  $1 $2"; }
ng(){ FAIL=$((FAIL+1)); echo "  FAIL  $1 $2"; }

echo "======================================================"
echo " nginx 运行态验证（真实加载/访问/SSL/反代）"
echo "======================================================"

# ============ 1 站点配置 ============
echo ""
echo "[1] 站点配置加载 + 访问"
T=/tmp/ngt1_$$
rm -rf $T; mkdir -p $T/conf/sites $T/www/site $T/logs
chmod 777 $T/logs
echo '<h1>SITE_OK</h1>' > $T/www/site/index.html

printf 'server {\n  listen 18088;\n  server_name site.local;\n  root %s/www/site;\n  index index.html;\n  location / { }\n}\n' "$T" > $T/conf/sites/site.conf
printf 'worker_processes 1;\nerror_log %s/logs/e.log warn;\npid %s/nginx.pid;\nevents { worker_connections 32; }\nhttp {\n  access_log off;\n  client_body_temp_path %s/logs/b;\n  proxy_temp_path %s/logs/p;\n  fastcgi_temp_path %s/logs/f;\n  uwsgi_temp_path %s/logs/u;\n  scgi_temp_path %s/logs/s;\n  include %s/conf/sites/*.conf;\n}\n' "$T" "$T" "$T" "$T" "$T" "$T" "$T" "$T" > $T/nginx.conf

if nginx -t -c $T/nginx.conf 2>&1 | grep -q "test is successful"; then
  ok "配置语法" "nginx -t 通过"
else
  ng "配置语法" "$(nginx -t -c $T/nginx.conf 2>&1 | tail -1)"
fi

nginx -c $T/nginx.conf 2>/dev/null
sleep 2
CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18088/ 2>/dev/null)
BODY=$(curl -s http://127.0.0.1:18088/ 2>/dev/null | head -1)
[ "$CODE" = "200" ] && ok "站点访问" "HTTP 200" || ng "站点访问" "HTTP $CODE"
echo "$BODY" | grep -q "SITE_OK" && ok "站点内容" "$BODY" || ng "站点内容" "$BODY"
nginx -s stop -c $T/nginx.conf 2>/dev/null
sleep 1; rm -rf $T

# ============ 2 SSL 证书 ============
echo ""
echo "[2] SSL 证书生成"
T=/tmp/ngt2_$$
mkdir -p $T
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -keyout $T/t.key -out $T/t.crt -subj "/CN=sitetest" >/dev/null 2>&1
[ -s $T/t.crt ] && ok "证书生成" "$(stat -c%s $T/t.crt) 字节" || ng "证书生成" "失败"
SUBJ=$(openssl x509 -in $T/t.crt -noout -subject 2>/dev/null)
echo "$SUBJ" | grep -q "CN" && ok "证书有效" "$SUBJ" || ng "证书有效" "$SUBJ"
rm -rf $T

# ============ 3 反向代理 ============
echo ""
echo "[3] 反向代理转发"
# 清理可能占用端口的旧进程
fuser -k 18087/tcp 18089/tcp 2>/dev/null
sleep 1
T=/tmp/ngt3_$
rm -rf $T; mkdir -p $T/conf/sites $T/logs $T/backend
chmod 777 $T/logs
echo '<h1>BACKEND_HIT</h1>' > $T/backend/index.html
cd $T/backend && python3 -m http.server 18089 >/dev/null 2>&1 &
cd - >/dev/null
BPID=$!
sleep 2

printf 'server {\n  listen 18087;\n  server_name proxy.local;\n  location / {\n    proxy_pass http://127.0.0.1:18089;\n    proxy_set_header Host $host;\n  }\n}\n' > $T/conf/sites/proxy.conf
printf 'worker_processes 1;\nerror_log %s/logs/e.log warn;\npid %s/nginx.pid;\nevents { worker_connections 32; }\nhttp {\n  access_log off;\n  client_body_temp_path %s/logs/b;\n  proxy_temp_path %s/logs/p;\n  fastcgi_temp_path %s/logs/f;\n  uwsgi_temp_path %s/logs/u;\n  scgi_temp_path %s/logs/s;\n  include %s/conf/sites/*.conf;\n}\n' "$T" "$T" "$T" "$T" "$T" "$T" "$T" "$T" > $T/nginx.conf

if nginx -t -c $T/nginx.conf 2>&1 | grep -q "test is successful"; then
  ok "反代配置" "语法通过"
else
  ng "反代配置" "$(nginx -t -c $T/nginx.conf 2>&1 | tail -1)"
fi

nginx -c $T/nginx.conf 2>/dev/null
sleep 2
CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18087/ 2>/dev/null)
BODY=$(curl -s http://127.0.0.1:18087/ 2>/dev/null | head -1)
[ "$CODE" = "200" ] && ok "反代转发" "HTTP 200" || ng "反代转发" "HTTP $CODE"
echo "$BODY" | grep -q "BACKEND_HIT" && ok "反代内容" "$BODY" || ng "反代内容" "$BODY"

nginx -s stop -c $T/nginx.conf 2>/dev/null
kill $BPID 2>/dev/null
sleep 1; rm -rf $T

echo ""
echo "======================================================"
echo " 结果: $PASS 通过, $FAIL 失败"
echo "======================================================"
[ $FAIL -eq 0 ] && exit 0 || exit 1
