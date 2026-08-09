import { useEffect, useState } from 'react'
import { Activity, BarChart3, Bot, ChevronLeft, ChevronRight, CircleHelp, Database, Download, HeartPulse, Menu, Send, X } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

type Row = Record<string, string | number | null>
type DashboardData = {metrics:{total_accounts:number;approved:number;pending:number;rejected:number;total_amount:number};status:Row[];network:Row[];monthly:Row[];channel:Row[]}
type BenefitsData = {metrics:{total_contributions:number;contributing_members:number;successful:number;pending:number;total_paid:number};status:Row[];vendor:Row[];monthly:Row[]}
type Pagination = {result_id:string;page:number;page_size:number;total:number}
type AskResult = {answer:string;sql:string;analysis_type:string;data:Row[];pagination?:Pagination;chart:{type:string;title:string;x_column:string;y_column:string;data:Row[]}}
type Domain = 'enrolments'|'benefits'
type Page = 'enrolments-dashboard'|'enrolments-ask'|'benefits-dashboard'|'benefits-ask'|'about'
const colors = ['#167d7f','#285c78','#f59e5b','#9f7aea','#e05d5d','#6cae75']
const number = new Intl.NumberFormat('en-US')
const compactNumber = new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1})
const dateParts = new Intl.DateTimeFormat('en-CA',{timeZone:'Africa/Kampala',year:'numeric',month:'2-digit',day:'2-digit'})
const dateOnly = (value:unknown) => {
  const text=String(value)
  if(!/^\d{4}-\d{2}-\d{2}T/.test(text))return text
  const parts=Object.fromEntries(dateParts.formatToParts(new Date(text)).map(part=>[part.type,part.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

async function api<T>(path:string, options?:RequestInit):Promise<T>{
  const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options?.headers}})
  const body=await response.json().catch(()=>({}))
  if(!response.ok) throw new Error(body.detail||'The request failed.')
  return body
}
const ErrorBox=({message}:{message:string})=><div className="error-box">{message}</div>
const ChartCard=({title,wide,children}:{title:string;wide?:boolean;children:React.ReactNode})=><article className={`chart-card ${wide?'wide':''}`}><h2>{title}</h2>{children}</article>

function Dashboard(){
  const [data,setData]=useState<DashboardData|null>(null),[error,setError]=useState('')
  useEffect(()=>{api<DashboardData>('/api/dashboard').then(setData).catch(e=>setError(e.message))},[])
  if(error)return <ErrorBox message={error}/>; if(!data)return <div className="loading">Loading live analytics…</div>
  const metrics=[['Total accounts',data.metrics.total_accounts,'all member records'],['Approved',data.metrics.approved,'active approvals'],['Pending',data.metrics.pending,'awaiting review'],['Rejected',data.metrics.rejected,'not approved'],['Collected amount',data.metrics.total_amount.toLocaleString(undefined,{minimumFractionDigits:2}),'approved accounts']]
  return <><Hero eyebrow="SmartLife enrolments" title="Enrolments dashboard" text="Member performance and activity at a glance." icon={<Activity size={38}/>}/><div className="metric-grid">{metrics.map(([label,value,hint])=><article className="metric" key={label}><span>{label}</span><strong>{typeof value==='number'?number.format(value):value}</strong><small>{hint}</small></article>)}</div><div className="chart-grid">
    <ChartCard title="Accounts by status"><ResponsiveContainer width="100%" height={280}><BarChart data={data.status} margin={{left:8,right:18}}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="status"/><YAxis allowDecimals={false} tickFormatter={v=>compactNumber.format(Number(v))} width={58}/><Tooltip formatter={v=>number.format(Number(v))}/><Bar dataKey="accounts" fill="#167d7f" radius={[7,7,0,0]}/></BarChart></ResponsiveContainer></ChartCard>
    <ChartCard title="Network distribution"><ResponsiveContainer width="100%" height={280}><PieChart><Pie data={data.network} dataKey="accounts" nameKey="network" innerRadius={58} outerRadius={96} paddingAngle={3}>{data.network.map((_,i)=><Cell key={i} fill={colors[i%colors.length]}/>)}</Pie><Tooltip/></PieChart></ResponsiveContainer></ChartCard>
    <ChartCard title="Monthly registrations" wide><ResponsiveContainer width="100%" height={280}><LineChart data={data.monthly} margin={{left:8,right:18}}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="month" tickFormatter={v=>String(v).slice(0,7)}/><YAxis allowDecimals={false} tickFormatter={v=>compactNumber.format(Number(v))} width={58}/><Tooltip formatter={v=>number.format(Number(v))}/><Line dataKey="registrations" stroke="#167d7f" strokeWidth={3} dot={false}/></LineChart></ResponsiveContainer></ChartCard>
    <ChartCard title="Accounts by channel" wide><ResponsiveContainer width="100%" height={280}><BarChart data={data.channel} layout="vertical"><CartesianGrid strokeDasharray="3 3" horizontal={false}/><XAxis type="number"/><YAxis dataKey="channel" type="category" width={100}/><Tooltip/><Bar dataKey="accounts" fill="#f59e5b" radius={[0,7,7,0]}/></BarChart></ResponsiveContainer></ChartCard>
  </div></>
}

function ResultChart({result}:{result:AskResult}){
  const c=result.chart
  if(!c.data.length||c.type==='none')return null
  let content:React.ReactNode
  if(result.analysis_type==='projection'){
    const label=(value:unknown)=>String(value).slice(0,7)
    const series=[...new Set(c.data.map(row=>row.series).filter(value=>value!=null).map(String))]
    const chartData=series.length?Array.from(c.data.reduce((points,row)=>{
      const period=String(row.period),name=String(row.series),point=points.get(period)||{period}
      point[`${name} actual`]=row.actual
      point[`${name} projected`]=row.projected
      points.set(period,point)
      return points
    },new Map<string,Row>()).values()):c.data
    content=<LineChart data={chartData} margin={{left:12,right:18}}>
      <CartesianGrid strokeDasharray="3 3" vertical={false}/>
      <XAxis dataKey="period" tickFormatter={label}/>
      <YAxis tickFormatter={value=>compactNumber.format(Number(value))} width={58}/>
      <Tooltip labelFormatter={label} formatter={(value,name)=>[number.format(Number(value)),String(name)]}/>
      {series.length?series.flatMap((name,index)=>[
        <Line key={`${name}-actual`} dataKey={`${name} actual`} name={`${name} — Historical`} stroke={colors[index%colors.length]} strokeWidth={3} dot={false} connectNulls={false}/>,
        <Line key={`${name}-projected`} dataKey={`${name} projected`} name={`${name} — Projected`} stroke={colors[index%colors.length]} strokeWidth={3} strokeDasharray="7 5" dot={{r:3}} connectNulls={false}/>
      ]):<><Line dataKey="actual" name="Historical" stroke="#285c78" strokeWidth={3} dot={false} connectNulls={false}/><Line dataKey="projected" name="Projected" stroke="#21a179" strokeWidth={3} strokeDasharray="7 5" dot={{r:3}} connectNulls={false}/></>}
    </LineChart>
  }else if(['pie','donut'].includes(c.type)){
    content=<PieChart><Pie data={c.data} dataKey={c.y_column} nameKey={c.x_column} innerRadius={c.type==='donut'?55:0} outerRadius={92}>{c.data.map((_,i)=><Cell key={i} fill={colors[i%colors.length]}/>)}</Pie><Tooltip formatter={(value,name)=>[number.format(Number(value)),String(name).replaceAll('_',' ')]}/></PieChart>
  }else if(c.type==='line'){
    content=<LineChart data={c.data} margin={{left:8,right:18,bottom:4}}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey={c.x_column} tickFormatter={dateOnly}/><YAxis tickFormatter={v=>compactNumber.format(Number(v))} width={58}/><Tooltip labelFormatter={dateOnly} formatter={(value,name)=>[number.format(Number(value)),String(name).replaceAll('_',' ')]}/><Line dataKey={c.y_column} stroke="#167d7f" strokeWidth={3}/></LineChart>
  }else{
    content=<BarChart data={c.data} margin={{left:8,right:18,bottom:4}}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey={c.x_column}/><YAxis tickFormatter={v=>compactNumber.format(Number(v))} width={58}/><Tooltip formatter={(value,name)=>[number.format(Number(value)),String(name).replaceAll('_',' ')]}/><Bar dataKey={c.y_column} fill="#167d7f" radius={[7,7,0,0]}/></BarChart>
  }
  return <ChartCard title={c.title||'Visual result'} wide><ResponsiveContainer width="100%" height={300}>{content}</ResponsiveContainer></ChartCard>
}

function DataTable({rows,pagination,onPage,loading}:{rows:Row[];pagination?:Pagination;onPage:(page:number)=>void;loading:boolean}){
  if(!rows.length)return null
  const columns=Object.keys(rows[0]),display=(value:Row[string])=>typeof value==='number'?number.format(value):String(value??'—')
  const pages=pagination?Math.max(1,Math.ceil(pagination.total/pagination.page_size)):1
  const first=pagination?(pagination.page-1)*pagination.page_size+1:1
  const last=pagination?Math.min(pagination.page*pagination.page_size,pagination.total):rows.length
  return <section className="result-table"><div className="table-tools"><div>{pagination?`Rows ${number.format(first)}–${number.format(last)} of ${number.format(pagination.total)}`:`${number.format(rows.length)} rows`}</div>{pagination&&<a className="download-button" href={`/api/results/${pagination.result_id}/download`}><Download size={17}/> Download all CSV</a>}</div><div className="table-wrap"><table><thead><tr>{columns.map(c=><th key={c}>{c.replaceAll('_',' ')}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={i}>{columns.map(c=><td key={c}>{display(row[c])}</td>)}</tr>)}</tbody></table></div>{pagination&&pages>1&&<div className="pagination"><button disabled={loading||pagination.page<=1} onClick={()=>onPage(pagination.page-1)}><ChevronLeft size={17}/> Previous</button><span>Page {number.format(pagination.page)} of {number.format(pages)}</span><button disabled={loading||pagination.page>=pages} onClick={()=>onPage(pagination.page+1)}>Next <ChevronRight size={17}/></button></div>}</section>
}

function AskDatabase({domain}:{domain:Domain}){
  const [questions,setQuestions]=useState<string[]>([]),[question,setQuestion]=useState(''),[result,setResult]=useState<AskResult|null>(null),[loading,setLoading]=useState(false),[pageLoading,setPageLoading]=useState(false),[error,setError]=useState('')
  useEffect(()=>{api<{questions:string[]}>(`/api/questions?domain=${domain}`).then(r=>setQuestions(r.questions)).catch(()=>{})},[domain])
  async function submit(e:React.FormEvent){e.preventDefault();if(!question.trim())return;setLoading(true);setError('');setResult(null);try{setResult(await api<AskResult>('/api/ask',{method:'POST',body:JSON.stringify({question,domain})}))}catch(err){setError(err instanceof Error?err.message:'Request failed.')}finally{setLoading(false)}}
  async function loadPage(page:number){if(!result?.pagination)return;setPageLoading(true);setError('');try{const next=await api<{data:Row[];page:number;page_size:number;total:number}>(`/api/results/${result.pagination.result_id}?page=${page}&page_size=${result.pagination.page_size}`);setResult({...result,data:next.data,pagination:{...result.pagination,...next}})}catch(err){setError(err instanceof Error?err.message:'Could not load the page.')}finally{setPageLoading(false)}}
  return <><header className="page-heading"><span>{domain}</span><h1>Ask the DB</h1></header><section className="ask-panel"><label htmlFor="demo">Start with an example</label><select id="demo" value="" onChange={e=>setQuestion(e.target.value)}><option value="">Choose a demonstration question…</option>{questions.map(q=><option key={q}>{q}</option>)}</select><form onSubmit={submit}><textarea value={question} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();e.currentTarget.form?.requestSubmit()}}} placeholder={domain==='benefits'?'How much has been paid successfully?':'Which network has the most members?'} rows={3}/><button disabled={loading||!question.trim()}>{loading?'Analysing…':<><Send size={18}/> Ask database</>}</button></form></section>{error&&<ErrorBox message={error}/>} {result&&<section className="results"><div className="answer"><Bot size={22}/><p>{result.answer}</p></div><ResultChart result={result}/><details><summary>Generated SQL</summary><pre>{result.sql}</pre></details><DataTable rows={result.data} pagination={result.pagination} onPage={loadPage} loading={pageLoading}/><p className="safety">SQL is validated and executed in a read-only transaction. Results are paginated for display.</p></section>}</>
}

function Hero({eyebrow,title,text,icon}:{eyebrow:string;title:string;text:string;icon:React.ReactNode}){return <section className="hero"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{text}</p></div>{icon}</section>}
function Benefits(){
  const [data,setData]=useState<BenefitsData|null>(null),[error,setError]=useState('')
  useEffect(()=>{api<BenefitsData>('/api/benefits').then(setData).catch(e=>setError(e.message))},[])
  if(error)return <ErrorBox message={error}/>;if(!data)return <div className="loading">Loading contribution analytics…</div>
  const metrics=[['Total contributions',data.metrics.total_contributions,'all contribution records'],['Contributing members',data.metrics.contributing_members,'unique NSSF numbers'],['Successful',data.metrics.successful,'completed contributions'],['Pending',data.metrics.pending,'awaiting completion'],['Total paid',data.metrics.total_paid.toLocaleString(undefined,{minimumFractionDigits:2}),'successful contributions']]
  return <><Hero eyebrow="SmartLife benefits" title="Benefits dashboard" text="Contribution activity, payment performance, and partner channels." icon={<HeartPulse size={40}/>}/><div className="metric-grid">{metrics.map(([label,value,hint])=><article className="metric" key={label}><span>{label}</span><strong>{typeof value==='number'?number.format(value):value}</strong><small>{hint}</small></article>)}</div><div className="chart-grid">
    <ChartCard title="Contributions by status"><ResponsiveContainer width="100%" height={280}><BarChart data={data.status} margin={{left:8,right:18}}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="status"/><YAxis allowDecimals={false} tickFormatter={v=>compactNumber.format(Number(v))} width={58}/><Tooltip formatter={v=>number.format(Number(v))}/><Bar dataKey="contributions" fill="#167d7f" radius={[7,7,0,0]}/></BarChart></ResponsiveContainer></ChartCard>
    <ChartCard title="Vendor distribution"><ResponsiveContainer width="100%" height={280}><PieChart><Pie data={data.vendor} dataKey="contributions" nameKey="vendor" innerRadius={58} outerRadius={96} paddingAngle={3}>{data.vendor.map((_,i)=><Cell key={i} fill={colors[i%colors.length]}/>)}</Pie><Tooltip/></PieChart></ResponsiveContainer></ChartCard>
    <ChartCard title="Monthly contribution volume" wide><ResponsiveContainer width="100%" height={280}><LineChart data={data.monthly} margin={{left:8,right:18}}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="month" tickFormatter={v=>String(v).slice(0,7)}/><YAxis tickFormatter={v=>compactNumber.format(Number(v))} width={58}/><Tooltip formatter={v=>number.format(Number(v))}/><Line dataKey="contributions" stroke="#285c78" strokeWidth={3} dot={false}/></LineChart></ResponsiveContainer></ChartCard>
    <ChartCard title="Monthly paid amount" wide><ResponsiveContainer width="100%" height={280}><LineChart data={data.monthly} margin={{left:8,right:18,bottom:4}}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="month" tickFormatter={v=>String(v).slice(0,7)}/><YAxis tickFormatter={v=>compactNumber.format(Number(v))} width={58}/><Tooltip formatter={v=>number.format(Number(v))}/><Line dataKey="paid_amount" stroke="#21a179" strokeWidth={3} dot={false}/></LineChart></ResponsiveContainer></ChartCard>
  </div></>
}
function About(){return <><Hero eyebrow="System architecture" title="About SmartLife Analytics" text="Live analytics and safe AI-assisted querying." icon={<CircleHelp size={40}/>}/><div className="about-grid"><article><Database/><h2>FastAPI backend</h2><p>Metrics and the database agent are exposed through a small, typed API.</p></article><article><BarChart3/><h2>React frontend</h2><p>A responsive dashboard renders interactive charts independently from Python.</p></article><article><Bot/><h2>Read-only agent</h2><p>Generated PostgreSQL is validated, time-limited, and capped before execution.</p></article></div></>}

export default function App(){
  const [page,setPage]=useState<Page>('enrolments-dashboard'),[menu,setMenu]=useState(false),[health,setHealth]=useState<{database:boolean;detail:string}|null>(null)
  useEffect(()=>{api<{database:boolean;detail:string}>('/api/health').then(setHealth).catch(()=>setHealth({database:false,detail:'API unavailable'}))},[])
  const nav=(next:Page)=>{setPage(next);setMenu(false)}
  return <div className="shell"><aside className={menu?'open':''}><div className="brand"><span><BarChart3/></span><div><strong>SmartLife</strong><small>Intelligence workspace</small></div></div><nav>
    <div className="nav-group"><div className="nav-heading"><BarChart3/> Enrolments</div><button className={page==='enrolments-dashboard'?'active':''} onClick={()=>nav('enrolments-dashboard')}><Activity/> Dashboard</button><button className={page==='enrolments-ask'?'active':''} onClick={()=>nav('enrolments-ask')}><Bot/> Ask the DB</button></div>
    <div className="nav-group"><div className="nav-heading"><HeartPulse/> Benefits</div><button className={page==='benefits-dashboard'?'active':''} onClick={()=>nav('benefits-dashboard')}><Activity/> Dashboard</button><button className={page==='benefits-ask'?'active':''} onClick={()=>nav('benefits-ask')}><Bot/> Ask the DB</button></div>
    <button className={`about-link ${page==='about'?'active':''}`} onClick={()=>nav('about')}><CircleHelp/> About</button>
  </nav><div className="connection"><i className={health?.database?'online':''}/><div><strong>{health?.database?'Database connected':'Database disconnected'}</strong><small>{health?.detail||'Checking connection…'}</small></div></div></aside><button className="menu" onClick={()=>setMenu(!menu)}>{menu?<X/>:<Menu/>}</button><main>{page==='enrolments-dashboard'?<Dashboard/>:page==='benefits-dashboard'?<Benefits/>:page==='enrolments-ask'?<AskDatabase key="enrolments" domain="enrolments"/>:page==='benefits-ask'?<AskDatabase key="benefits" domain="benefits"/>:<About/>}</main></div>
}
