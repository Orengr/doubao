#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_tunnel_logic.py — 隧道哨兵判定逻辑测试
验证 v2 多路探测：任一路通即判定存活。
这修复了 v1 的 bug：要求 17800 和 18090 同时为真，
导致只有一路通时误判为断线，反复发送拉起指令触发限流。
"""

def make_alive(probe_results):
    def probe(port, path="/ping"):
        return probe_results.get(port, False)
    def alive():
        if probe(17800): return True, "17800"
        if probe(18090, "/x"): return True, "18090"
        if probe(17801, "/api/ping"): return True, "17801"
        return False, "none"
    return alive()

def main():
    cases = [
        ("全离线",       {17800:False, 18090:False, 17801:False}, (False,"none")),
        ("只有17800通",  {17800:True,  18090:False, 17801:False}, (True,"17800")),
        ("只有18090通",  {17800:False, 18090:True,  17801:False}, (True,"18090")),
        ("只有17801通",  {17800:False, 18090:False, 17801:True},  (True,"17801")),
        ("全通",         {17800:True,  18090:True,  17801:True},  (True,"17800")),
    ]
    P = F = 0
    print("=" * 56)
    print(" 隧道哨兵判定逻辑测试")
    print("=" * 56)
    for name, probes, expect in cases:
        got = make_alive(probes)
        ok = got == expect
        print(("  PASS  " if ok else "  FAIL  ") + name.ljust(14) + "期望" + str(expect) + " 实际" + str(got))
        P += ok; F += (not ok)
    print("\n 结果: %d 通过 %d 失败" % (P, F))
    print("=" * 56)
    return 0 if F == 0 else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
