from __future__ import annotations
import json
from wsgiref.simple_server import make_server
from typing import Callable
from .gateway import Gateway

HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EdgeSynapse: Towards Leaky-Spike Transmission for Sustainable Edge Sensing Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{box-sizing:border-box}
body{margin:0;padding:18px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:#0f172a;color:#e5e7eb}
.header{background:linear-gradient(135deg,#4f46e5,#6366f1);padding:16px 20px;border-radius:12px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center}
.header-title{font-size:22px;font-weight:600}
.header-sub{font-size:12px;opacity:.9}
.badge{font-size:11px;padding:4px 10px;border-radius:999px;background:rgba(15,23,42,.25)}
.top-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.card{background:#020617;border-radius:10px;padding:10px 12px;border:1px solid rgba(148,163,184,.3)}
.card-label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9ca3af;margin-bottom:2px}
.card-value{font-size:22px;font-weight:600;color:#e5e7eb}
.card-sub{font-size:11px;color:#9ca3af}
.controls{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:14px}
.control{display:flex;align-items:center;font-size:11px;color:#9ca3af}
.control label{margin-right:6px}
.control input{font-size:11px;padding:3px 6px;border-radius:6px;border:1px solid rgba(148,163,184,.4);background:#020617;color:#e5e7eb;min-width:60px}
.layout{display:grid;grid-template-columns:2.4fr 1.6fr;gap:14px;align-items:flex-start}
@media(max-width:900px){.layout{grid-template-columns:1fr}}
.panel{background:#020617;border-radius:10px;padding:10px 12px;border:1px solid rgba(148,163,184,.3);margin-bottom:12px}
.panel-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.panel-title{font-size:12px;font-weight:500;color:#e5e7eb}
.panel-meta{font-size:11px;color:#9ca3af}
.chart-block{height:230px;position:relative}
canvas{width:100%;height:100%}
.node-list{display:flex;flex-wrap:wrap;gap:6px;font-size:11px}
.node-pill{padding:3px 8px;border-radius:999px;border:1px solid rgba(148,163,184,.5);cursor:pointer;user-select:none}
.node-pill.active{background:#4f46e5;border-color:#4f46e5;color:#e5e7eb}
.pill-muted{opacity:.7}
.kpi-strong{color:#22c55e}
.kpi-warn{color:#f97316}
.kpi-bad{color:#ef4444}
</style>
</head>
<body>
<div class="header">
<div>
<div class="header-title">EdgeSynapse: Towards Leaky-Spike Transmission for Sustainable Edge Sensing Dashboard</div>
<div class="header-sub">LIF-based spiking, inhibition and LoRa energy model</div>
</div>
<div class="badge" id="lastUpdated">waiting data</div>
</div>
<div class="top-grid">
<div class="card">
<div class="card-label">Active nodes</div>
<div class="card-value" id="kpiNodes">-</div>
</div>
<div class="card">
<div class="card-label">Messages</div>
<div class="card-value" id="kpiMessages">-</div>
<div class="card-sub" id="kpiRate">0 msg/s</div>
</div>
<div class="card">
<div class="card-label">Aggregator</div>
<div class="card-value" id="kpiAggFires">-</div>
<div class="card-sub" id="kpiAggTheta">θ: -</div>
</div>
<div class="card">
<div class="card-label">Suppressed spikes</div>
<div class="card-value" id="kpiSuppressed">-</div>
</div>
<div class="card">
  <div class="card-label">Collided messages</div>
  <div class="card-value" id="kpiPairs">-</div>
  <div class="card-sub" id="kpiCollMode">mode: -</div>
</div>
<div class="card">
<div class="card-label">Inhibition</div>
<div class="card-value" id="kpiBeta">β=1.0</div>
<div class="card-sub" id="kpiInhState">idle</div>
</div>
</div>
<div class="controls">
<div class="control">
<label for="refresh">Refresh</label>
<input id="refresh" type="number" min="1" value="2">
<span style="margin-left:4px">s</span>
</div>
<div class="control">
<label for="sigma">Spike σ</label>
<input id="sigma" type="number" step="0.1" value="2.0">
</div>
<div class="control">
<label for="pause">Pause</label>
<input id="pause" type="checkbox">
</div>
</div>
<div class="layout">
<div>
<div class="panel">
<div class="panel-header">
<div class="panel-title">Sensor values per node</div>
<div class="panel-meta" id="rangeInfo">range: -</div>
</div>
<div class="chart-block">
<canvas id="tsChart"></canvas>
</div>
</div>
<div class="panel">
<div class="panel-header">
<div class="panel-title">Nodes</div>
<div class="panel-meta" id="nodeMeta">selected: -</div>
</div>
<div class="node-list" id="nodeList"></div>
</div>
</div>
<div>
<div class="panel">
<div class="panel-header">
<div class="panel-title">Energy per node</div>
<div class="panel-meta">Joules</div>
</div>
<div class="chart-block">
<canvas id="energyChart"></canvas>
</div>
</div>
<div class="panel">
<div class="panel-header">
  <div class="panel-title">Collided messages per node</div>
  <div class="panel-meta">messages whose airtime overlapped other nodes</div>
</div>
<div class="chart-block">
<canvas id="collisionChart"></canvas>
</div>
</div>
<div class="panel">
<div class="panel-header">
<div class="panel-title">Message rate</div>
<div class="panel-meta">last 60 s</div>
</div>
<div class="chart-block">
<canvas id="rateChart"></canvas>
</div>
</div>
</div>
</div>
<script>
let tsChart;
let energyChart;
let collisionChart;
let rateChart;
let selectedNodes={};
let rateHistory=[];
let fetchTimer=null;

function initCharts(){
const tsCtx=document.getElementById("tsChart").getContext("2d");
const enCtx=document.getElementById("energyChart").getContext("2d");
const colCtx=document.getElementById("collisionChart").getContext("2d");
const rateCtx=document.getElementById("rateChart").getContext("2d");
tsChart=new Chart(tsCtx,{type:"line",data:{labels:[],datasets:[]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:true,position:"top",labels:{font:{size:11}}}},scales:{x:{ticks:{maxRotation:0,font:{size:10}}},y:{ticks:{font:{size:10}}}}}});
energyChart=new Chart(enCtx,{type:"bar",data:{labels:[],datasets:[{label:"Energy (J)",data:[]}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{font:{size:10}}},y:{ticks:{font:{size:10}},beginAtZero:true}}}});
collisionChart=new Chart(colCtx,{type:"bar",data:{labels:[],datasets:[{label:"Overlapping TX",data:[]}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{font:{size:10}}},y:{ticks:{font:{size:10}},beginAtZero:true,precision:0}}}});
rateChart=new Chart(rateCtx,{type:"line",data:{labels:[],datasets:[{label:"msg/s",data:[]}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{maxRotation:0,font:{size:10}}},y:{ticks:{font:{size:10}},beginAtZero:true}}}});
}

function formatTime(ts){
if(!ts)return"";
const d=new Date(ts);
return d.toLocaleTimeString("en-GB",{hour12:false});
}

function buildNodeList(nodes){
const ids=Object.keys(nodes).sort(function(a,b){return Number(a)-Number(b)});
const container=document.getElementById("nodeList");
container.innerHTML="";
let selected=0;
ids.forEach(function(id){
if(selectedNodes[id]===undefined)selectedNodes[id]=true;
const span=document.createElement("span");
span.className="node-pill"+(selectedNodes[id]?" active":"");
span.textContent="Node "+id;
span.onclick=function(){
selectedNodes[id]=!selectedNodes[id];
if(selectedNodes[id])span.classList.add("active");else span.classList.remove("active");
};
container.appendChild(span);
if(selectedNodes[id])selected+=1;
});
document.getElementById("nodeMeta").textContent="selected: "+selected+"/"+ids.length;
}

function updateCharts(metrics){
const ts=metrics.timestamps||[];
const nodes=metrics.nodes||{};
buildNodeList(nodes);
const datasets=[];
let globalMin=null;
let globalMax=null;

Object.keys(nodes).forEach(function(id){
if(!selectedNodes[id])return;
const vals=nodes[id].values||[];
datasets.push({label:"Node "+id,data:vals,borderWidth:1,pointRadius:0.5});
for(let i=0;i<vals.length;i++){
const v=vals[i];
if(v===null||v===undefined)continue;
if(globalMin===null||v<globalMin)globalMin=v;
if(globalMax===null||v>globalMax)globalMax=v;
}
});

tsChart.data.labels=ts.map(formatTime);
tsChart.data.datasets=datasets;
if(globalMin!==null&&globalMax!==null){
if(globalMin===globalMax){globalMin=globalMin-1;globalMax=globalMax+1;}
const span=globalMax-globalMin;
const pad=0.05*span;
tsChart.options.scales.y.min=globalMin-pad;
tsChart.options.scales.y.max=globalMax+pad;
document.getElementById("rangeInfo").textContent="range: "+globalMin.toFixed(2)+" to "+globalMax.toFixed(2);
}else{
tsChart.options.scales.y.min=undefined;
tsChart.options.scales.y.max=undefined;
document.getElementById("rangeInfo").textContent="range: -";
}
tsChart.update();

const summary=metrics.summary||{};
const nodeIds=Object.keys(summary).sort(function(a,b){return Number(a)-Number(b)});
energyChart.data.labels=nodeIds.map(function(id){return"Node "+id});
energyChart.data.datasets[0].data=nodeIds.map(function(id){return summary[id].energy_total||0});
energyChart.update();

collisionChart.data.labels=nodeIds.map(function(id){return"Node "+id});
collisionChart.data.datasets[0].data=nodeIds.map(function(id){return summary[id].collisions||0});
collisionChart.update();

const nowIso=metrics.last_updated_iso;
if(nowIso)document.getElementById("lastUpdated").textContent=formatTime(nowIso);

const rate=metrics.msgs_per_sec||0;
const now=new Date().toISOString();
rateHistory.push({ts:now,rate:rate});
if(rateHistory.length>60)rateHistory=rateHistory.slice(rateHistory.length-60);
rateChart.data.labels=rateHistory.map(function(r){return formatTime(r.ts)});
rateChart.data.datasets[0].data=rateHistory.map(function(r){return r.rate});
rateChart.update();
}

function updateKpis(metrics){
const nodes=metrics.nodes||{};
document.getElementById("kpiNodes").textContent=Object.keys(nodes).length;
document.getElementById("kpiMessages").textContent=metrics.total_messages||0;
const rate=metrics.msgs_per_sec||0;
const rateLabel=document.getElementById("kpiRate");
rateLabel.textContent=rate.toFixed(2)+" msg/s";
if(rate<0.1){rateLabel.className="card-sub kpi-strong";}
else if(rate<1.0){rateLabel.className="card-sub kpi-warn";}
else{rateLabel.className="card-sub kpi-bad";}

const agg=metrics.aggregator||{};
document.getElementById("kpiAggFires").textContent=agg.fires||0;
document.getElementById("kpiAggTheta").textContent="θ: "+(agg.theta!=null?Number(agg.theta).toFixed(1):"-");
document.getElementById("kpiSuppressed").textContent=agg.suppressed_total||0;

document.getElementById("kpiPairs").textContent = metrics.total_collided_messages || 0;
const modeRaw=metrics.collision_mode||"-";
let modeLabel=modeRaw;
if(modeRaw==="spikes")modeLabel="spike packets only";
if(modeRaw==="all")modeLabel="all packets";
document.getElementById("kpiCollMode").textContent="mode: "+modeLabel;

const inh=metrics.inhibition||{};
const beta=inh.beta!=null?Number(inh.beta):1.0;
document.getElementById("kpiBeta").textContent="β="+beta.toFixed(2);
const now=timeNowSeconds();
const expiry=inh.expiry_ts||0;
document.getElementById("kpiInhState").textContent=expiry>now?"active":"idle";
}

function timeNowSeconds(){return Date.now()/1000.0;}

async function fetchMetrics(){
if(document.getElementById("pause").checked)return;
try{
const r=await fetch("/metrics");
const m=await r.json();
updateKpis(m);
updateCharts(m);
}catch(e){}
}

function scheduleFetch(){
if(fetchTimer!==null)clearInterval(fetchTimer);
let interval=parseInt(document.getElementById("refresh").value,10);
if(!interval||interval<1)interval=2;
fetchTimer=setInterval(fetchMetrics,interval*1000);
}

document.getElementById("refresh").addEventListener("change",scheduleFetch);
initCharts();
scheduleFetch();
fetchMetrics();
</script>
</body>
</html>
"""

def make_app(gateway: "Gateway") -> Callable:
    def app(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == "/metrics":
            try:
                metrics = gateway.snapshot_metrics()
                data = json.dumps(metrics)
                headers = [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(data))),
                    ("Access-Control-Allow-Origin", "*"),
                ]
                start_response("200 OK", headers)
                return [data.encode("utf-8")]
            except Exception as e:
                payload = json.dumps({"error": str(e)})
                start_response(
                    "500 Internal Server Error", [("Content-Type", "application/json")]
                )
                return [payload.encode("utf-8")]
        if path == "/":
            headers = [("Content-Type", "text/html; charset=utf-8")]
            start_response("200 OK", headers)
            return [HTML.encode("utf-8")]
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"Not Found"]
    return app

def run_http(gateway: "Gateway", host: str, port: int) -> None:
    app = make_app(gateway)
    server = make_server(host, port, app)
    server.serve_forever()
