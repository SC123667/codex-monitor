#!/usr/bin/env python3
"""
Codex Code Monitor - Web 仪表板（标准库实现）

默认端口 8081，避免与 Claude Monitor(8080) 冲突。
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from codex_monitor_core import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MonitorConfig,
    build_usage_summary,
    default_codex_sessions_dir,
)


_lock = threading.Lock()
_latest_data: Dict[str, Any] = {}
_latest_events: List[Dict[str, Any]] = []
_last_error: Optional[str] = None
_DASHBOARD_BUILD = datetime.fromtimestamp(Path(__file__).stat().st_mtime).isoformat(sep=" ", timespec="seconds")


def _update_loop(
    sessions_dir: Path,
    config: MonitorConfig,
    cwd_filter: Optional[str],
    interval: float,
):
    global _latest_data, _latest_events, _last_error
    while True:
        try:
            data = build_usage_summary(
                sessions_dir=sessions_dir,
                config=config,
                cwd_filter=cwd_filter,
                now=datetime.now(),
                include_events=True,
            )
            events = data.pop("events", [])
            with _lock:
                _latest_data = data
                _latest_events = events if isinstance(events, list) else []
                _last_error = None
        except Exception as e:
            with _lock:
                _last_error = str(e)
        time.sleep(max(1.0, float(interval)))


HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Codex Code Monitor</title>
  <style>
    :root{
      --bg:#0b1020;--card:#121a33;--muted:#98a2b3;--text:#e5e7eb;--accent:#7c3aed;
      --border:rgba(255,255,255,.08);
    }
    body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,"Noto Sans","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:linear-gradient(180deg,#070a14,#0b1020 40%,#070a14);color:var(--text);}
    .wrap{max-width:1100px;margin:28px auto;padding:0 16px;}
    .top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;}
    h1{font-size:22px;margin:0 0 6px;}
    .sub{color:var(--muted);font-size:13px;}
    .btns{display:flex;gap:10px;align-items:center;}
    button{background:var(--accent);border:none;color:white;padding:9px 12px;border-radius:10px;cursor:pointer;font-weight:600;}
    button.secondary{background:transparent;border:1px solid var(--border);color:var(--text);}
    .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;margin-top:14px;}
    .card{grid-column:span 3;background:rgba(18,26,51,.88);border:1px solid var(--border);border-radius:14px;padding:14px;}
    .card.wide{grid-column:span 12;}
    .k{color:var(--muted);font-size:12px;}
    .v{font-size:20px;margin-top:6px;font-weight:800;}
    .row{display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;}
    .pill{padding:6px 10px;border-radius:999px;background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.35);font-size:12px;color:#ddd;}
    .tabs{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:-2px 0 10px;}
    .tab{background:transparent;border:1px solid var(--border);color:var(--text);padding:7px 10px;border-radius:999px;font-weight:700;}
    .tab.active{background:rgba(124,58,237,.18);border-color:rgba(124,58,237,.45);}
    .pane[hidden]{display:none;}
    table{width:100%;border-collapse:collapse;margin-top:10px;}
    th,td{border-bottom:1px solid var(--border);padding:9px 8px;text-align:left;font-size:13px;}
    th{color:var(--muted);font-weight:700;}
    .right{text-align:right;}
    .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;}
    .muted{color:var(--muted);}
    .err{color:#fecaca;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);padding:10px 12px;border-radius:12px;margin-top:12px;display:none;}
    select,input{background:rgba(0,0,0,.25);border:1px solid var(--border);color:var(--text);padding:8px 10px;border-radius:10px;outline:none;}
    input{min-width:240px;}
    canvas{width:100%;height:260px;display:block;border:1px solid var(--border);border-radius:12px;background:rgba(0,0,0,.18);}
    .hint{color:var(--muted);font-size:12px;margin-top:8px;}
    .nowrap{white-space:nowrap;}
    @media (max-width: 900px){ .card{grid-column:span 6;} }
    @media (max-width: 520px){ .card{grid-column:span 12;} }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1>Codex Code Monitor</h1>
        <div class="sub" id="meta">加载中...</div>
      </div>
      <div class="btns">
        <button class="secondary" id="btnRefresh">手动刷新</button>
        <button id="btnDownload">下载 JSON</button>
      </div>
    </div>

    <div class="err" id="errBox"></div>

    <div class="grid">
      <div class="card">
        <div class="k">估算费用（USD）</div>
        <div class="v mono" id="totalCost">$0.000000</div>
        <div class="sub">调用 <span class="mono" id="totalCalls">-</span> · 按 token_count 增量去重</div>
      </div>

      <div class="card">
        <div class="k">总 Token</div>
        <div class="v mono" id="totalTokens">-</div>
        <div class="sub" id="totalDetail">-</div>
      </div>

      <div class="card">
        <div class="k">最近 5 小时</div>
        <div class="v mono" id="h5Tokens">-</div>
        <div class="sub">调用 <span class="mono" id="h5Calls">-</span> · 费用 <span class="mono" id="h5Cost">$0.000000</span></div>
        <div class="sub muted" id="h5Detail">-</div>
      </div>

	      <div class="card">
	        <div class="k">5 小时窗口用量</div>
	        <div class="v mono" id="rlUsed">-</div>
	        <div class="sub" id="rlReset">-</div>
	      </div>

	      <div class="card wide">
	        <div class="top" style="align-items:center;">
	          <div>
	            <div class="k">趋势（折线图）</div>
	            <div class="sub muted" id="chartSubtitle">-</div>
	          </div>
	          <div class="btns">
	            <select id="chartMetric" aria-label="metric">
	              <option value="tokens">Tokens</option>
	              <option value="cost">Cost (USD)</option>
	            </select>
	            <select id="chartRange" aria-label="range">
	              <option value="5h">最近 5 小时</option>
	              <option value="24h">最近 24 小时</option>
	              <option value="week">本周</option>
	              <option value="7d">最近 7 天</option>
	              <option value="30d">最近 30 天</option>
	              <option value="all">全部</option>
	            </select>
	          </div>
	        </div>
	        <canvas id="trendChart" width="1100" height="260"></canvas>
	        <div class="hint" id="chartHint">提示：横轴为时间，纵轴为所选指标；数据来自本机 ~/.codex/sessions 日志。</div>
	      </div>

	      <div class="card wide">
	        <div class="tabs" role="tablist" aria-label="详情">
	          <button class="tab active" data-tab="models" type="button">按模型</button>
	          <button class="tab" data-tab="cwd" type="button">工作目录</button>
	          <button class="tab" data-tab="recent" type="button">最近调用</button>
	          <button class="tab" data-tab="h5" type="button">5小时明细</button>
	          <button class="tab" data-tab="week" type="button">本周明细</button>
	          <button class="tab" data-tab="history" type="button">历史明细</button>
	        </div>

	        <div class="pane" id="pane-models">
	          <div class="k">按模型统计（Top 20）</div>
	          <table id="tblModels">
	            <thead>
	              <tr>
	                <th>模型</th>
	                <th class="right">Calls</th>
	                <th class="right">Tokens · Cost</th>
	              </tr>
	            </thead>
	            <tbody></tbody>
	          </table>
	        </div>

	        <div class="pane" id="pane-cwd" hidden>
	          <div class="k">Top 工作目录（Top 15）</div>
	          <table id="tblCwd">
	            <thead>
	              <tr>
	                <th>cwd</th>
	                <th class="right">Calls</th>
	                <th class="right">Tokens · Cost</th>
	              </tr>
	            </thead>
	            <tbody></tbody>
	          </table>
	        </div>

	        <div class="pane" id="pane-recent" hidden>
	          <div class="k">最近调用（最近 12 条）</div>
	          <table id="tblRecent">
	            <thead>
	              <tr>
	                <th>时间</th>
	                <th>模型</th>
	                <th class="right">Tokens · Cost</th>
	              </tr>
	            </thead>
	            <tbody></tbody>
	          </table>
	          <div class="sub muted" style="margin-top:8px;" id="note"></div>
	        </div>

	        <div class="pane" id="pane-h5" hidden>
	          <div class="row" style="align-items:center;justify-content:space-between;">
	            <div class="k">最近 5 小时明细</div>
	            <div class="sub muted nowrap" id="h5MetaDetail">-</div>
	          </div>
	          <table id="tblH5Hours">
	            <thead>
	              <tr>
	                <th>小时</th>
	                <th class="right">Calls</th>
	                <th class="right">Tokens · Cost</th>
	              </tr>
	            </thead>
	            <tbody></tbody>
	          </table>
	          <div class="k" style="margin-top:12px;">最近 5 小时 · Top 模型</div>
	          <table id="tblH5Models">
	            <thead>
	              <tr>
	                <th>模型</th>
	                <th class="right">Calls</th>
	                <th class="right">Tokens · Cost</th>
	              </tr>
	            </thead>
	            <tbody></tbody>
	          </table>
	        </div>

	        <div class="pane" id="pane-week" hidden>
	          <div class="row" style="align-items:center;justify-content:space-between;">
	            <div class="k">本周明细</div>
	            <div class="sub muted nowrap" id="weekMetaDetail">-</div>
	          </div>
	          <table id="tblWeekDays">
	            <thead>
	              <tr>
	                <th>日期</th>
	                <th class="right">Calls</th>
	                <th class="right">Tokens · Cost</th>
	              </tr>
	            </thead>
	            <tbody></tbody>
	          </table>
	          <div class="k" style="margin-top:12px;">本周 · Top 模型</div>
	          <table id="tblWeekModels">
	            <thead>
	              <tr>
	                <th>模型</th>
	                <th class="right">Calls</th>
	                <th class="right">Tokens · Cost</th>
	              </tr>
	            </thead>
	            <tbody></tbody>
	          </table>
	        </div>

	        <div class="pane" id="pane-history" hidden>
	          <div class="row" style="align-items:center;justify-content:space-between;">
	            <div class="k">历史明细（分页）</div>
	            <div class="sub muted nowrap" id="historyMeta">-</div>
	          </div>
	          <div class="row">
	            <input id="historyQuery" type="text" placeholder="过滤：model / cwd 关键字" />
	            <select id="historyLimit">
	              <option value="50">50 / 页</option>
	              <option value="200" selected>200 / 页</option>
	              <option value="500">500 / 页</option>
	            </select>
	            <button class="secondary" id="btnHistorySearch" type="button">查询</button>
	            <button class="secondary" id="btnHistoryPrev" type="button">上一页</button>
	            <button class="secondary" id="btnHistoryNext" type="button">下一页</button>
	            <button class="secondary" id="btnHistoryTop" type="button">回到最新</button>
	          </div>
	          <table id="tblHistory">
	            <thead>
	              <tr>
	                <th>时间</th>
	                <th>模型</th>
	                <th>Tokens · Cost</th>
	                <th>来源</th>
	                <th>cwd</th>
	              </tr>
	            </thead>
	            <tbody></tbody>
	          </table>
	        </div>
	      </div>
	    </div>
	  </div>

	  <script>
	    const fmtInt = (n) => {
	      try { return Number(n).toLocaleString('en-US'); } catch(e) { return String(n); }
	    };
	    const fmtUsd = (n) => {
	      try { return '$' + Number(n).toFixed(6); } catch(e) { return String(n); }
	    };
	    const fmtFloat = (n, digits=3) => {
	      try { return Number(n).toFixed(digits); } catch(e) { return String(n); }
	    };

	    let latestSummary = null;
	    let activeTab = 'models';

	    const CHART_METRIC_KEY = 'codex_monitor_chart_metric';
	    const CHART_RANGE_KEY = 'codex_monitor_chart_range';

	    function shortXLabel(s){
	      const str = String(s || '');
	      if(str.length >= 13 && str.includes(':')){ // YYYY-MM-DD HH:00
	        return str.slice(5, 13); // MM-DD HH
	      }
	      if(str.length >= 10){
	        return str.slice(5); // MM-DD
	      }
	      return str || '-';
	    }

	    function drawLineChart(canvas, labels, values, metric){
	      if(!canvas) return;
	      const ctx = canvas.getContext('2d');
	      if(!ctx) return;

	      const rect = canvas.getBoundingClientRect();
	      const dpr = window.devicePixelRatio || 1;
	      const w = Math.max(1, rect.width);
	      const h = Math.max(1, rect.height);
	      canvas.width = Math.floor(w * dpr);
	      canvas.height = Math.floor(h * dpr);
	      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
	      ctx.clearRect(0, 0, w, h);

	      const padL = 54, padR = 14, padT = 12, padB = 32;
	      const plotW = Math.max(1, w - padL - padR);
	      const plotH = Math.max(1, h - padT - padB);

	      const n = Array.isArray(values) ? values.length : 0;
	      if(n <= 0){
	        ctx.fillStyle = 'rgba(255,255,255,.55)';
	        ctx.font = '12px ui-monospace, Menlo, monospace';
	        ctx.fillText('暂无数据', padL, padT + 12);
	        return;
	      }

	      let maxV = 0;
	      for(const v of values){ maxV = Math.max(maxV, Number(v) || 0); }
	      if(!isFinite(maxV) || maxV <= 0) maxV = 1;

	      const xAt = (i) => padL + (n === 1 ? 0 : (i * plotW / (n - 1)));
	      const yAt = (v) => padT + (1 - (Math.max(0, Number(v) || 0) / maxV)) * plotH;

	      // axes
	      ctx.strokeStyle = 'rgba(255,255,255,.12)';
	      ctx.lineWidth = 1;
	      ctx.beginPath();
	      ctx.moveTo(padL, padT);
	      ctx.lineTo(padL, padT + plotH);
	      ctx.lineTo(padL + plotW, padT + plotH);
	      ctx.stroke();

	      // grid (3 lines)
	      ctx.strokeStyle = 'rgba(255,255,255,.06)';
	      ctx.beginPath();
	      for(const t of [0.25, 0.5, 0.75]){
	        const y = padT + plotH * t;
	        ctx.moveTo(padL, y);
	        ctx.lineTo(padL + plotW, y);
	      }
	      ctx.stroke();

	      // y labels
	      ctx.fillStyle = 'rgba(255,255,255,.55)';
	      ctx.font = '12px ui-monospace, Menlo, monospace';
	      const topLabel = (metric === 'cost') ? fmtUsd(maxV) : fmtInt(Math.round(maxV));
	      ctx.fillText(topLabel, 8, padT + 12);
	      ctx.fillText(metric === 'cost' ? fmtUsd(0) : fmtInt(0), 8, padT + plotH);

	      // x labels (first/last)
	      const first = shortXLabel(labels[0]);
	      const last = shortXLabel(labels[n - 1]);
	      ctx.fillText(first, padL, h - 10);
	      const lastW = ctx.measureText(last).width;
	      ctx.fillText(last, Math.max(padL, w - padR - lastW), h - 10);

	      // line
	      ctx.strokeStyle = 'rgba(124,58,237,.85)';
	      ctx.lineWidth = 2;
	      ctx.beginPath();
	      for(let i = 0; i < n; i++){
	        const x = xAt(i);
	        const y = yAt(values[i]);
	        if(i === 0) ctx.moveTo(x, y);
	        else ctx.lineTo(x, y);
	      }
	      ctx.stroke();

	      // last point
	      ctx.fillStyle = 'rgba(124,58,237,.95)';
	      ctx.beginPath();
	      ctx.arc(xAt(n - 1), yAt(values[n - 1]), 3, 0, Math.PI * 2);
	      ctx.fill();
	    }

		    function renderChart(data){
		      const canvas = document.getElementById('trendChart');
		      const metricEl = document.getElementById('chartMetric');
		      const rangeEl = document.getElementById('chartRange');
		      if(!canvas || !metricEl || !rangeEl) return;

		      const metric = metricEl.value || 'tokens';
		      const range = rangeEl.value || '24h';
		      const series = (data && data.series) ? data.series : {};
		      const windows = (data && data.windows) ? data.windows : {};

		      let rows = [];
		      let label = '';
		      if(range === '5h'){
		        const w = windows.last_5_hours || {};
		        rows = Array.isArray(w.by_hour) ? w.by_hour : [];
		        label = '最近 5 小时';
		      }else if(range === '24h'){
		        rows = Array.isArray(series.by_hour) ? series.by_hour : [];
		        rows = rows.slice(-24);
		        label = '最近 24 小时';
		      }else if(range === 'week'){
		        const w = windows.this_week || {};
		        rows = Array.isArray(w.by_date) ? w.by_date : [];
		        label = '本周';
		      }else{
		        rows = Array.isArray(series.by_date) ? series.by_date : [];
		        if(range === '7d') rows = rows.slice(-7);
		        if(range === '30d') rows = rows.slice(-30);
		        label = (range === 'all') ? '按天（全部）' : (range === '7d' ? '最近 7 天' : '最近 30 天');
		      }

		      const labels = rows.map((r) => (range === '5h' || range === '24h' ? r.hour : r.date));
		      const values = rows.map((r) => metric === 'cost' ? (r.estimated_cost_usd || 0) : (r.total_tokens || 0));
		      drawLineChart(canvas, labels, values, metric);

		      const sub = document.getElementById('chartSubtitle');
		      if(sub){
		        const m = metric === 'cost' ? 'Cost (USD)' : 'Tokens';
		        const sumTokens = rows.reduce((a, r) => a + (Number(r.total_tokens) || 0), 0);
		        const sumCost = rows.reduce((a, r) => a + (Number(r.estimated_cost_usd) || 0), 0);
		        sub.textContent = `${label} · ${m} · 合计 ${fmtInt(sumTokens)} · ${fmtUsd(sumCost)} · 点数 ${fmtInt(values.length)}`;
		      }
		    }

		    function renderWindows(data){
		      const windows = data.windows || {};

		      // last 5 hours
		      const h5 = windows.last_5_hours || {};
		      const h5Total = h5.total || {};
		      const h5Meta = document.getElementById('h5MetaDetail');
		      if(h5Meta){
		        h5Meta.textContent = `调用 ${fmtInt(h5Total.calls || 0)} · Tokens ${fmtInt(h5Total.total_tokens || 0)} · Cost ${fmtUsd(h5Total.estimated_cost_usd || 0)}`;
		      }

		      const h5Hours = Array.isArray(h5.by_hour) ? h5.by_hour : [];
		      const tbodyH5Hours = document.querySelector('#tblH5Hours tbody');
		      if(tbodyH5Hours){
		        tbodyH5Hours.innerHTML = '';
		        if(h5Hours.length === 0){
		          tbodyH5Hours.innerHTML = `<tr><td class="muted" colspan="3">暂无数据</td></tr>`;
		        }else{
		          for(const r of h5Hours){
		            const tr = document.createElement('tr');
		            const title = `${r.hour || '-'}  in ${fmtInt(r.input_tokens || 0)} (cached ${fmtInt(r.cached_input_tokens || 0)}) / out ${fmtInt(r.output_tokens || 0)}`;
		            tr.innerHTML = `<td class="mono nowrap" title="${title}">${r.hour || '-'}</td><td class="right mono">${fmtInt(r.calls || 0)}</td><td class="right mono" title="${title}">${fmtInt(r.total_tokens || 0)} · ${fmtUsd(r.estimated_cost_usd || 0)}</td>`;
		            tbodyH5Hours.appendChild(tr);
		          }
		        }
		      }

		      const h5Models = Array.isArray(h5.by_model) ? h5.by_model : [];
		      const tbodyH5Models = document.querySelector('#tblH5Models tbody');
		      if(tbodyH5Models){
		        tbodyH5Models.innerHTML = '';
		        if(h5Models.length === 0){
		          tbodyH5Models.innerHTML = `<tr><td class="muted" colspan="3">暂无数据</td></tr>`;
		        }else{
		          for(const r of h5Models){
		            const title = `in ${fmtInt(r.input_tokens || 0)} (cached ${fmtInt(r.cached_input_tokens || 0)}) / out ${fmtInt(r.output_tokens || 0)}`;
		            const tr = document.createElement('tr');
		            tr.innerHTML = `<td class="mono" title="${title}">${r.model || '-'}</td><td class="right mono">${fmtInt(r.calls || 0)}</td><td class="right mono" title="${title}">${fmtInt(r.total_tokens || 0)} · ${fmtUsd(r.estimated_cost_usd || 0)}</td>`;
		            tbodyH5Models.appendChild(tr);
		          }
		        }
		      }

		      // this week
		      const wk = windows.this_week || {};
		      const wkTotal = wk.total || {};
		      const wkRange = wk.range || {};
		      const wkMeta = document.getElementById('weekMetaDetail');
		      if(wkMeta){
		        const start = wkRange.start ? String(wkRange.start).slice(0, 10) : '-';
		        const end = wkRange.end ? String(wkRange.end).slice(0, 10) : '-';
		        wkMeta.textContent = `${start} ~ ${end} · 调用 ${fmtInt(wkTotal.calls || 0)} · Tokens ${fmtInt(wkTotal.total_tokens || 0)} · Cost ${fmtUsd(wkTotal.estimated_cost_usd || 0)}`;
		      }

		      const wkDays = Array.isArray(wk.by_date) ? wk.by_date : [];
		      const tbodyWkDays = document.querySelector('#tblWeekDays tbody');
		      if(tbodyWkDays){
		        tbodyWkDays.innerHTML = '';
		        if(wkDays.length === 0){
		          tbodyWkDays.innerHTML = `<tr><td class="muted" colspan="3">暂无数据</td></tr>`;
		        }else{
		          for(const r of wkDays){
		            const title = `in ${fmtInt(r.input_tokens || 0)} (cached ${fmtInt(r.cached_input_tokens || 0)}) / out ${fmtInt(r.output_tokens || 0)}`;
		            const tr = document.createElement('tr');
		            tr.innerHTML = `<td class="mono nowrap" title="${title}">${r.date || '-'}</td><td class="right mono">${fmtInt(r.calls || 0)}</td><td class="right mono" title="${title}">${fmtInt(r.total_tokens || 0)} · ${fmtUsd(r.estimated_cost_usd || 0)}</td>`;
		            tbodyWkDays.appendChild(tr);
		          }
		        }
		      }

		      const wkModels = Array.isArray(wk.by_model) ? wk.by_model : [];
		      const tbodyWkModels = document.querySelector('#tblWeekModels tbody');
		      if(tbodyWkModels){
		        tbodyWkModels.innerHTML = '';
		        if(wkModels.length === 0){
		          tbodyWkModels.innerHTML = `<tr><td class="muted" colspan="3">暂无数据</td></tr>`;
		        }else{
		          for(const r of wkModels){
		            const title = `in ${fmtInt(r.input_tokens || 0)} (cached ${fmtInt(r.cached_input_tokens || 0)}) / out ${fmtInt(r.output_tokens || 0)}`;
		            const tr = document.createElement('tr');
		            tr.innerHTML = `<td class="mono" title="${title}">${r.model || '-'}</td><td class="right mono">${fmtInt(r.calls || 0)}</td><td class="right mono" title="${title}">${fmtInt(r.total_tokens || 0)} · ${fmtUsd(r.estimated_cost_usd || 0)}</td>`;
		            tbodyWkModels.appendChild(tr);
		          }
		        }
		      }
		    }

	    // history (paged)
	    let historyOffset = 0;
	    let historyTotal = 0;
	    async function fetchHistory(){
	      const qEl = document.getElementById('historyQuery');
	      const limitEl = document.getElementById('historyLimit');
	      const q = (qEl ? qEl.value : '') || '';
	      const limit = Number(limitEl ? limitEl.value : 200) || 200;

	      const url = `/api/events?offset=${historyOffset}&limit=${limit}&q=${encodeURIComponent(q)}`;
	      const res = await fetch(url, {cache:'no-store'});
	      const payload = await res.json();

	      if(payload && payload.error){
	        setError(payload.error);
	      }else{
	        setError(null);
	      }

	      const total = Number(payload.total || 0) || 0;
	      const offset = Number(payload.offset || 0) || 0;
	      const events = Array.isArray(payload.events) ? payload.events : [];
	      historyTotal = total;

	      const meta = document.getElementById('historyMeta');
	      if(meta){
	        const start = total === 0 ? 0 : (offset + 1);
	        const end = Math.min(offset + limit, total);
	        meta.textContent = `${start}-${end} / ${fmtInt(total)}` + (q ? ` · 过滤: ${q}` : '');
	      }

	      const btnPrev = document.getElementById('btnHistoryPrev');
	      const btnNext = document.getElementById('btnHistoryNext');
	      if(btnPrev) btnPrev.disabled = (offset <= 0);
	      if(btnNext) btnNext.disabled = (offset + limit >= total);

	      const tbody = document.querySelector('#tblHistory tbody');
	      if(!tbody) return;
	      tbody.innerHTML = '';
	      for(const e of events){
	        const tr = document.createElement('tr');
	        const tokens = e.tokens || {};
	        const cost = e.cost_usd || {};
	        const rates = e.rates_per_million || {};

	        const totalLine = `${fmtInt(tokens.total || 0)} · ${fmtUsd(cost.total || 0)}`;
	        const tokLine = `in ${fmtInt(tokens.input || 0)} (cached ${fmtInt(tokens.cached_input || 0)}) / out ${fmtInt(tokens.output || 0)}`;
	        const costLine = `in ${fmtUsd(cost.uncached_input || 0)} + cached ${fmtUsd(cost.cached_input || 0)} + out ${fmtUsd(cost.output || 0)}`;
	        const rateLine = `rate in ${fmtFloat(rates.input || 0)} / cached ${fmtFloat(rates.cached_input || 0)} / out ${fmtFloat(rates.output || 0)} $/1M`;

	        tr.innerHTML = `
	          <td class="mono nowrap">${e.timestamp || '-'}</td>
	          <td class="mono">${e.model || '-'}</td>
	          <td>
	            <div class="mono">${totalLine}</div>
	            <div class="sub muted">${tokLine}</div>
	            <div class="sub muted">${costLine}</div>
	            <div class="sub muted">${rateLine}</div>
	          </td>
	          <td class="mono nowrap">${e.pricing_source || '-'}</td>
	          <td class="mono" title="${e.cwd || ''}">${e.cwd || '-'}</td>
	        `;
	        tbody.appendChild(tr);
	      }
	    }

	    function setError(msg){
	      const box = document.getElementById('errBox');
	      if(!msg){ box.style.display='none'; box.textContent=''; return; }
      box.style.display='block';
      box.textContent = msg;
    }

		    function render(data){
		      latestSummary = data;
		      const src = data.source || {};
		      const srv = data.server || {};
		      document.getElementById('meta').textContent = `更新时间: ${data.generated_at || '-'} · 文件: ${src.files ?? '-'} · 日志: ${src.sessions_dir || '-'}` + (src.cwd_filter ? ` · 过滤: ${src.cwd_filter}` : '') + ` · build: ${srv.build || '-'}`;

      const total = data.total || {};
      document.getElementById('totalTokens').textContent = fmtInt(total.total_tokens || 0);
      document.getElementById('totalCalls').textContent = fmtInt(total.calls || 0);
      document.getElementById('totalCost').textContent = fmtUsd(total.estimated_cost_usd || 0);
      document.getElementById('totalDetail').textContent = `输入 ${fmtInt(total.input_tokens||0)} (缓存 ${fmtInt(total.cached_input_tokens||0)}) / 输出 ${fmtInt(total.output_tokens||0)}`;

      const h5 = data.five_hour || {};
      document.getElementById('h5Tokens').textContent = fmtInt(h5.total_tokens || 0);
      document.getElementById('h5Calls').textContent = fmtInt(h5.calls || 0);
      const h5CostEl = document.getElementById('h5Cost');
      if(h5CostEl){ h5CostEl.textContent = fmtUsd(h5.estimated_cost_usd || 0); }
      document.getElementById('h5Detail').textContent = `输入 ${fmtInt(h5.input_tokens||0)} (缓存 ${fmtInt(h5.cached_input_tokens||0)}) / 输出 ${fmtInt(h5.output_tokens||0)}`;

      const rl = (data.rate_limits || {}).primary || null;
      if(rl){
        const used = (rl.used_percent === null || rl.used_percent === undefined) ? '-' : (String(rl.used_percent) + '%');
        document.getElementById('rlUsed').textContent = used;
        document.getElementById('rlReset').textContent = `重置: ${rl.resets_at || '-'}  剩余: ${rl.remaining_seconds ?? '-'}s`;
      }else{
        document.getElementById('rlUsed').textContent='-';
        document.getElementById('rlReset').textContent='-';
	      }

	      // models
	      const byModel = data.by_model || {};
	      const models = Object.entries(byModel).map(([k,v]) => [k, v]).sort((a,b) => (b[1].total_tokens||0)-(a[1].total_tokens||0));
	      const tbodyM = document.querySelector('#tblModels tbody');
	      tbodyM.innerHTML = '';
	      for(const [model, st] of models.slice(0, 20)){
	        const tr = document.createElement('tr');
	        tr.innerHTML = `<td class="mono">${model}</td><td class="right mono">${fmtInt(st.calls||0)}</td><td class="right mono">${fmtInt(st.total_tokens||0)} · ${fmtUsd(st.estimated_cost_usd||0)}</td>`;
	        tbodyM.appendChild(tr);
	      }

	      // recent
	      const recent = Array.isArray(data.recent_calls) ? data.recent_calls : [];
	      const tbodyR = document.querySelector('#tblRecent tbody');
	      tbodyR.innerHTML = '';
	      for(const r of recent.slice(0, 12)){
	        const tr = document.createElement('tr');
	        tr.innerHTML = `<td class="mono nowrap">${r.timestamp || '-'}</td><td class="mono">${r.model || '-'}</td><td class="right mono">${fmtInt(r.total_tokens||0)} · ${fmtUsd(r.estimated_cost_usd||0)}</td>`;
	        tbodyR.appendChild(tr);
	      }

	      // cwd
	      const byCwd = data.by_cwd || {};
	      const cwds = Object.entries(byCwd).map(([k,v]) => [k, v]).sort((a,b) => (b[1].total_tokens||0)-(a[1].total_tokens||0));
	      const tbodyC = document.querySelector('#tblCwd tbody');
	      tbodyC.innerHTML = '';
	      for(const [cwd, st] of cwds.slice(0, 15)){
	        const tr = document.createElement('tr');
	        tr.innerHTML = `<td class="mono" title="${cwd}">${cwd}</td><td class="right mono">${fmtInt(st.calls||0)}</td><td class="right mono">${fmtInt(st.total_tokens||0)} · ${fmtUsd(st.estimated_cost_usd||0)}</td>`;
	        tbodyC.appendChild(tr);
	      }

		      document.getElementById('note').textContent = data.note || '';
		      renderChart(data);
		      renderWindows(data);
		    }

    async function fetchData(){
      const res = await fetch('/api/data', {cache:'no-store'});
      const payload = await res.json();
      if(payload && payload.error){
        setError(payload.error);
      }else{
        setError(null);
      }
      render(payload.data || payload);
    }

	    async function refreshNow(){
	      await fetch('/api/refresh', {method:'POST'});
	      await fetchData();
	      if(activeTab === 'history'){
	        await fetchHistory();
	      }
	    }

	    document.getElementById('btnRefresh').addEventListener('click', refreshNow);
		    const TAB_KEY = 'codex_monitor_active_tab';
		    function setTab(name){
		      let wanted = name || 'models';
		      if(!document.getElementById('pane-' + wanted)){
		        wanted = 'models';
		      }
		      activeTab = wanted;
		      document.querySelectorAll('.tab').forEach((btn) => {
		        const isActive = (btn.dataset.tab === wanted);
		        btn.classList.toggle('active', isActive);
		      });
	      document.querySelectorAll('.pane').forEach((pane) => {
	        pane.hidden = (pane.id !== ('pane-' + wanted));
	      });
	      try { localStorage.setItem(TAB_KEY, wanted); } catch(e) {}
	      if(wanted === 'history'){
	        fetchHistory();
	      }
	    }
	    document.querySelectorAll('.tab').forEach((btn) => {
	      btn.addEventListener('click', () => setTab(btn.dataset.tab));
	    });
	    try { setTab(localStorage.getItem(TAB_KEY) || 'models'); } catch(e) { setTab('models'); }

	    // chart controls
	    const metricEl = document.getElementById('chartMetric');
	    const rangeEl = document.getElementById('chartRange');
	    try { metricEl.value = localStorage.getItem(CHART_METRIC_KEY) || 'tokens'; } catch(e) {}
	    try { rangeEl.value = localStorage.getItem(CHART_RANGE_KEY) || '24h'; } catch(e) {}
	    metricEl.addEventListener('change', () => {
	      try { localStorage.setItem(CHART_METRIC_KEY, metricEl.value); } catch(e) {}
	      if(latestSummary) renderChart(latestSummary);
	    });
	    rangeEl.addEventListener('change', () => {
	      try { localStorage.setItem(CHART_RANGE_KEY, rangeEl.value); } catch(e) {}
	      if(latestSummary) renderChart(latestSummary);
	    });
	    window.addEventListener('resize', () => {
	      if(latestSummary) renderChart(latestSummary);
	    });

	    // history controls
	    const qEl = document.getElementById('historyQuery');
	    const limitEl = document.getElementById('historyLimit');
	    document.getElementById('btnHistorySearch').addEventListener('click', () => { historyOffset = 0; fetchHistory(); });
	    document.getElementById('btnHistoryPrev').addEventListener('click', () => {
	      const limit = Number(limitEl.value || 200) || 200;
	      historyOffset = Math.max(0, historyOffset - limit);
	      fetchHistory();
	    });
	    document.getElementById('btnHistoryNext').addEventListener('click', () => {
	      const limit = Number(limitEl.value || 200) || 200;
	      historyOffset = historyOffset + limit;
	      if(historyOffset >= historyTotal) historyOffset = Math.max(0, historyTotal - limit);
	      fetchHistory();
	    });
	    document.getElementById('btnHistoryTop').addEventListener('click', () => { historyOffset = 0; fetchHistory(); });
	    limitEl.addEventListener('change', () => { historyOffset = 0; fetchHistory(); });
	    qEl.addEventListener('keydown', (ev) => {
	      if(ev.key === 'Enter'){ historyOffset = 0; fetchHistory(); }
	    });

	    document.getElementById('btnDownload').addEventListener('click', async () => {
	      const res = await fetch('/api/data', {cache:'no-store'});
	      const payload = await res.json();
	      const data = payload.data || payload;
      const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'codex_monitor_summary.json';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    });

	    fetchData();
	    setInterval(fetchData, 5000);
	  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return

        if parsed.path == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return

        if parsed.path == "/api/data":
            with _lock:
                data = dict(_latest_data)
                err = _last_error
            data.setdefault(
                "server",
                {
                    "pid": os.getpid(),
                    "build": _DASHBOARD_BUILD,
                },
            )
            payload: Dict[str, Any]
            if err:
                payload = {"error": err, "data": data}
            else:
                payload = data
            self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if parsed.path == "/api/events":
            qs = parse_qs(parsed.query or "")
            q = (qs.get("q", [None])[0] or "").strip()
            model = (qs.get("model", [None])[0] or "").strip()
            cwd = (qs.get("cwd", [None])[0] or "").strip()

            try:
                offset = int(qs.get("offset", ["0"])[0] or 0)
            except Exception:
                offset = 0
            try:
                limit = int(qs.get("limit", ["200"])[0] or 200)
            except Exception:
                limit = 200

            offset = max(0, offset)
            limit = max(1, min(500, limit))

            with _lock:
                events = _latest_events
                err = _last_error

            filtered = events
            if q:
                ql = q.lower()
                filtered = [
                    e
                    for e in filtered
                    if ql in str(e.get("model", "")).lower() or ql in str(e.get("cwd", "")).lower()
                ]
            if model:
                ml = model.lower()
                filtered = [e for e in filtered if str(e.get("model", "")).lower() == ml]
            if cwd:
                cl = cwd.lower()
                filtered = [e for e in filtered if cl in str(e.get("cwd", "")).lower()]

            total = len(filtered)
            page = filtered[offset : offset + limit]
            payload = {
                "error": err,
                "total": total,
                "offset": offset,
                "limit": limit,
                "events": page,
            }
            self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        self._send(404, b"not found\n")

    def do_POST(self):
        global _latest_data, _latest_events, _last_error
        parsed = urlparse(self.path)
        if parsed.path != "/api/refresh":
            self._send(404, b"not found\n")
            return

        # 允许带 query 参数覆盖 cwd_filter（可选）
        qs = parse_qs(parsed.query or "")
        override_cwd = qs.get("cwd", [None])[0]

        try:
            # 使用最近一次配置做一次同步刷新
            with _lock:
                current = dict(_latest_data)
            sessions_dir = Path(current.get("source", {}).get("sessions_dir", str(default_codex_sessions_dir())))
            cwd_filter = override_cwd or current.get("source", {}).get("cwd_filter")
            cfg = MonitorConfig.load()
            data = build_usage_summary(
                sessions_dir=sessions_dir,
                config=cfg,
                cwd_filter=cwd_filter,
                now=datetime.now(),
                include_events=True,
            )
            events = data.pop("events", [])
            with _lock:
                _latest_data = data
                _latest_events = events if isinstance(events, list) else []
                _last_error = None
            self._send(200, b"ok\n")
        except Exception as e:
            with _lock:
                _last_error = str(e)
            self._send(500, str(e).encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Codex Code Monitor - Web 仪表板")
    parser.add_argument("--host", default=None, help=f"监听地址（默认 {DEFAULT_HOST}）")
    parser.add_argument("--port", type=int, default=None, help=f"监听端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--sessions-dir", default=None, help="会话日志目录（默认：~/.codex/sessions）")
    parser.add_argument("--config", default=None, help="配置文件路径（默认：~/.codex/monitor_config.json 或 $CODEX_MONITOR_CONFIG）")
    parser.add_argument("--cwd", default=None, help="仅统计该目录(含子目录)下的会话")
    parser.add_argument("--update-interval", type=float, default=3.0, help="后台更新间隔（秒）")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir).expanduser() if args.sessions_dir else default_codex_sessions_dir()
    config_path = Path(args.config).expanduser() if args.config else None
    cfg = MonitorConfig.load(config_path)

    host = args.host or cfg.host or DEFAULT_HOST
    port = args.port or cfg.port or DEFAULT_PORT

    # 先做一次初始数据
    global _latest_data, _latest_events
    initial = build_usage_summary(
        sessions_dir=sessions_dir,
        config=cfg,
        cwd_filter=args.cwd,
        now=datetime.now(),
        include_events=True,
    )
    _latest_events = initial.pop("events", [])
    _latest_data = initial

    t = threading.Thread(
        target=_update_loop,
        args=(sessions_dir, cfg, args.cwd, args.update_interval),
        daemon=True,
    )
    t.start()

    server = HTTPServer((host, int(port)), Handler)
    url = f"http://{host}:{port}"
    print(f"✅ Web 仪表板已启动：{url}")
    print(f"📁 sessions: {sessions_dir}")
    if args.cwd:
        print(f"🔎 cwd 过滤: {args.cwd}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
