/* tools/titles.js —— 工具标题：脚本名中文化、参数摘要、图标与 diff 统计格式化。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function pickFileHint(args){if(!args||typeof args!=="object")return "";
const keys=["file","request_file","payload_file","path","old_path","new_path","source_path","dest_path","source","patch_file"];
for(let k of keys){let v=args[k];if(v===undefined&&args["--"+k]!==undefined)v=args["--"+k];
if(typeof v==="string"&&v){const parts=v.replace(/\\/g,"/").split("/");return parts[parts.length-1]||v;}}
return "";}
function parseToolPayload(args){
if(!args||typeof args!=="object")return null;
let p=args.payload;
if(typeof p==="string"){try{return JSON.parse(p);}catch(e){return null;}}
if(p&&typeof p==="object")return p;
let pj=args["--payload"];
if(typeof pj==="string"){try{return JSON.parse(pj);}catch(e){return null;}}
return null;}
function argGet(args,name){
if(!args||typeof args!=="object")return undefined;
const k=name.indexOf("--")===0?name:"--"+name;
if(args[k]!==undefined)return args[k];
if(args[name]!==undefined)return args[name];
return undefined;}
function baseNameOnly(p){
if(!p||typeof p!=="string")return "";
const parts=p.replace(/\\/g,"/").split("/");
return parts[parts.length-1]||p;}
/** 步骤标题用：优先末两段路径，避免过长 */
function pathLeaf(p){
/* 先统一成 `/` 便于切段，切完再按本机习惯还原成 `\`。
   不还原的话，同一个路径在走 pathLeaf 的标题里显示 `E:/test.txt`、
   在直接用原样的标题里显示 `E:\test.txt`，看起来像两个不同的路径。 */
const s=String(p||"").trim().replace(/\\/g,"/");
if(!s)return "";
const parts=s.split("/").filter(Boolean);
if(parts.length<=2)return (parts.join("/")||s).replace(/\//g,"\\");
return parts.slice(-2).join("/").replace(/\//g,"\\");}
function inferLangFromPath(path){
const n=baseNameOnly(String(path||"")).toLowerCase();
const m=n.match(/\.([a-z0-9_+-]+)$/i);
if(!m)return "";
const ext=m[1];
const mp={py:'python',js:'javascript',ts:'typescript',tsx:'typescript',jsx:'javascript',json:'json',yml:'yaml',yaml:'yaml',xml:'xml',html:'html',css:'css',md:'markdown',java:'java',go:'go',rs:'rust',sql:'sql',sh:'bash',bat:'batch',ps1:'powershell',txt:''};
return mp[ext]!==undefined?mp[ext]:"";}
function renderPreviewText(text,lang){
const t=String(text||"");
if(lang)return highlightCode(t,lang);
return escapeHtml(t);
}
function buildToolTitleParts(script,args,full){
function take(text,n){
var s=String(text==null?"":text);
if(full)return s;
return s.length>n?s.slice(0,n):s;
}
function takeDots(text,n){
var s=String(text==null?"":text);
if(full||s.length<=n)return s;
return s.slice(0,n)+"…";
}
const s=(script+"").toLowerCase();
// confirm_id 提交时请求参数纯净（无 path），但预览已把 confirm_id→path 记入缓存；
// 此处仅构造展示视图（副本），不修改原始 args，展示策略与预览/ review 一致（从 args 取路径）
const cid=argGet(args,"confirm_id");
if(cid&&!argGet(args,"path")&&!argGet(args,"source_path")&&!argGet(args,"dest_path")){
const dp=(window.confirmPathCache&&window.confirmPathCache[String(cid).trim()])||"";
if(dp){const merged=Object.assign({},args);merged.path=dp;args=merged;}}
if(s.indexOf("read_file")>=0){
const path=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(path)||"（未指定 path）";
const ls=argGet(args,"line_start"), le=argGet(args,"line_end");
const sc=argGet(args,"start_column"), ec=argGet(args,"end_column");
const chs=argGet(args,"char_start"), che=argGet(args,"char_end");
let rng="";
if(ls!=null&&le!=null){
if(sc!=null&&ec!=null)rng=" L"+ls+":"+sc+"-"+le+":"+ec;
else rng=" L"+ls+"-"+le;
}else if(chs!=null||che!=null){
rng=" §"+(chs!=null?chs:0)+"-"+(che!=null?che:"EOF");
}
return {main:"读取文件",fname:leaf+rng};}
if(s.indexOf("write_file")>=0){
const path=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(path)||"（未指定 path）";
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
const co=!!argGet(args,"create_only");
const cx=co?" · create_only":"";
return {main:dry?"预览修改":"提交修改",fname:leaf+cx};}
if(s.indexOf("replace_in_file")>=0){
const path=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(path)||"（未指定 path）";
const rs=argGet(args,"region_start"), re=argGet(args,"region_end");
const ls=argGet(args,"line_start"), le=argGet(args,"line_end");
const sc=argGet(args,"start_column"), ec=argGet(args,"end_column");
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
const rules=argGet(args,"rules");
let mode="字面替换",extra="";
if(rs!=null&&re!=null){mode="区间";extra=" §"+rs+"–"+re;}
else if(ls!=null&&le!=null&&sc!=null&&ec!=null){mode="矩形";extra=" L"+ls+":"+sc+"–"+le+":"+ec;}
else if(Array.isArray(rules)&&rules.length)mode="规则×"+rules.length;
return {main:dry?"预览修改":"提交修改",fname:leaf+" · "+mode+extra};}
if(s.indexOf("grep_files")>=0){
const root=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(root)||takeDots(root,36);
const pat=take(argGet(args,"pattern"),40);
const re=!!argGet(args,"regex");
return {main:"搜索"+(re?"（正则）":"（字面）"),fname:leaf+(pat?" · /"+pat+"/":"")};}
if(s.indexOf("find_in_file")>=0){
const path=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(path)||"（未指定 path）";
const occ=argGet(args,"occurrence");
const re=!!argGet(args,"regex");
const o=occ!=null&&occ!==0?" · 第"+(Number(occ)+1)+"处":"";
return {main:"定位"+(re?"（正则）":"（字面）"),fname:leaf+o};}
if(s.indexOf("read_write")>=0){
const src=pathLeaf(String(argGet(args,"source_path")||""));
const dst=pathLeaf(String(argGet(args,"dest_path")||""));
const ls=argGet(args,"line_start"), le=argGet(args,"line_end");
const chs=argGet(args,"char_start"), che=argGet(args,"char_end");
let rng="";
if(ls!=null&&le!=null)rng=" L"+ls+"–"+le;
else if(chs!=null||che!=null)rng=" §"+(chs!=null?chs:0)+"–"+(che!=null?che:"");
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
return {main:dry?"预览修改":"提交修改",fname:(src||"?")+(dst?" → "+dst:"")+rng};}
if(s.indexOf("delete_file")>=0){
const leaf=String(argGet(args,"path")||"").trim()||"（未指定 path）";
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
return {main:dry?"预览删除":"删除文件",fname:leaf};}
if(s.indexOf("apply_patch")>=0){
const root=pathLeaf(String(argGet(args,"path")||""))||".";
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
const pf=baseNameOnly(String(argGet(args,"patch_file")||""));
const pt=String(argGet(args,"patch_text")||"");
const hint=pf|| (pt?"内联补丁":"补丁");
return {main:dry?"预览修改":"提交修改",fname:root+" · "+hint};}
if(s.indexOf("run_command")>=0){
const cwd=pathLeaf(String(argGet(args,"cwd")||""));
const cmd=String(argGet(args,"command")||"").replace(/\s+/g," ").trim().slice(0,72);
return {main:"执行命令",fname:(cwd?cwd+" · ":"")+(cmd||"（空命令）")};}
if(s.indexOf("python_inline")>=0){
const cwd=pathLeaf(String(argGet(args,"cwd")||""));
const c0=String(argGet(args,"code")||"").replace(/\s+/g," ").trim();
const c=take(c0,48);
return {main:"执行命令",fname:(cwd?cwd+" · ":"")+(c+(!full&&c0.length>48?"…":"")||"（无 code）")};}
if(s.indexOf("archive")>=0){
const act=String(argGet(args,"action")||"").toLowerCase();
const src=pathLeaf(String(argGet(args,"source")||""))||"（未指定 source）";
const dst=pathLeaf(String(argGet(args,"dest")||""));
const am=act==="list"?"列出压缩包":act==="extract"?"预览解压":act==="create"?"预览打包":"压缩包操作";
return {main:am,fname:src+(dst?" · → "+dst:"")};}
if(s.indexOf("data_table")>=0){
const act=String(argGet(args,"action")||"");
const src=pathLeaf(String(argGet(args,"source")||""))||"表格";
const sh=take(argGet(args,"sheet"),16);
return {main:"处理表格 · "+(act||"?"),fname:src+(sh?" · "+sh:"")};}
if(s.indexOf("todo_list")>=0){
const act=String(argGet(args,"action")||"");
return {main:"Todo-List",fname:act||"query"};}
if(s.indexOf("approval_confirm")>=0){
const d=take(argGet(args,"option_desc"),40);
return {main:"审批",fname:d||"（无描述）"};}
if(s.indexOf("user_confirm")>=0){
const t=take(argGet(args,"title"),40);
return {main:"等待用户确认",fname:t||"（无标题）"};}
if(s.indexOf("run_type")>=0){
const rt=String(argGet(args,"run_type")||"").trim().toLowerCase();
return {main:rt?"切换运行模式":"查询运行模式",fname:rt||"auto/plan/execute"};}
if(s.indexOf("glob_files")>=0){
const et=String(argGet(args,"entry_type")||"").toLowerCase();
const scope=(et==="dir"?"仅目录":et==="all"?"全部":"")+(et==="file"||!et?"文件":"");
return {main:"列出路径"+(scope?"（"+scope+"）":""),fname:chatGlobSummary(args)};}
if(s.indexOf("web_fetch")>=0){
const url=String(argGet(args,"url")||"").trim();
return {main:"网页",fname:url};}
if(s.indexOf("file_search")>=0){
const pat=take(argGet(args,"pattern"),40);
const root=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(root)||takeDots(root,28);
return {main:"全文搜索"+(argGet(args,"regex")?"（正则）":"（字面）"),fname:leaf+(pat?" · /"+pat+"/":"")};}
if(s.indexOf("ip_geolocate")>=0){
const ip=String(argGet(args,"ip")||"").trim();
return {main:"定位公网地区"+(ip?" · "+ip:""),fname:""};}
if(s.indexOf("open_meteo")>=0){
const loc=String(argGet(args,"location")||"").slice(0,20);
const la=String(argGet(args,"latitude")||"").trim();
const lo=String(argGet(args,"longitude")||"").trim();
if(la&&lo)return {main:"查询天气 · "+la+","+lo,fname:""};
return {main:"查询天气"+(loc?" · "+loc:""),fname:""};}
if(s.indexOf("regex_locate")>=0){
const pat=take(argGet(args,"pattern"),48);
const tgt=pathLeaf(String(argGet(args,"path")||""));
const glob=String(argGet(args,"glob_pattern")||"");
return {main:"正则检索",fname:(tgt||"?")+(pat?" · /"+pat+"/":"")+(glob&&glob!=="*"?" · "+glob:"")};}
if(s.indexOf("file_ops")>=0){
const act=String(argGet(args,"action")||"").toLowerCase();
const src=String(argGet(args,"source")||"").trim();
const dst=String(argGet(args,"dest")||"").trim();
const arrow=src+(dst?" → "+dst:"");
if(act==="delete")return {main:"预览删除",fname:src||"见参数"};
if(act==="copy")return {main:"预览复制",fname:arrow};
if(act==="move")return {main:"预览移动",fname:arrow};
if(act==="rename")return {main:"预览重命名",fname:arrow};
return {main:"预览文件操作",fname:src};}
if(s.indexOf("text_diff")>=0){
const lf=baseNameOnly(String(argGet(args,"left_file")||""));
const rf=baseNameOnly(String(argGet(args,"right_file")||""));
if(lf||rf)return {main:"对比 · "+(lf||"?")+" ↔ "+(rf||"?"),fname:""};
return {main:"对比文本",fname:""};}
if(s.indexOf("git_workspace")>=0){
const root=pathLeaf(String(argGet(args,"path")||""))||".";
const mode=String(argGet(args,"mode")||"worktree");
return {main:"查看 Git",fname:root+" · "+mode};}
if(s.indexOf("image_ocr")>=0){
const src=pathLeaf(String(argGet(args,"source")||""))||"（未指定 source）";
const eng=String(argGet(args,"engine")||"auto").toLowerCase();
const reg=String(argGet(args,"region")||"").trim();
const extra=(eng&&eng!=="auto")?" · "+eng:"";
const rg=reg?" · 区域 "+reg:"";
return {main:"识别图片文字",fname:src+extra+rg};}
if(s.indexOf("env_probe")>=0)return {main:"探测运行环境",fname:""};
if(s.indexOf("diagnos")>=0){
const root=pathLeaf(String(argGet(args,"path")||""))||".";
return {main:"统一诊断",fname:root};}
if(s.indexOf("review_conclusion")>=0){
const fn=String(argGet(args,"file_name")||"").trim();
const full=String(argGet(args,"path")||"").trim();
var shown=fn;
if(full&&(!fn||fn===baseNameOnly(full)||(fn.indexOf("/")<0&&fn.indexOf("\\")<0)))shown=full;
return {main:"Review",fname:shown||full};}
if(s.indexOf("file_undo")>=0){
const ac=String(argGet(args,"action")||"").trim();
const fp=pathLeaf(String(argGet(args,"path")||""))||"";
let ts="";
const mid=String(argGet(args,"mod_id")||"").trim();
/* 版本目录名的形状由 file_safety._version_dir_name 产出：`YYYYMMDD_HHMMSS_mmm_序号_随机`。
   按固定形状取，不靠数段数 —— 名字里增删一段（例如加同毫秒序号）就会取错位置，
   卡片标题上显示的就不再是时刻。 */
if(mid){const mv=/_(\d{6})_\d{3}_\d{4}_[0-9a-z]+$/.exec(mid);if(mv)ts=mv[1].slice(0,2)+":"+mv[1].slice(2,4)+":"+mv[1].slice(4,6);}
const label=ac==="list"?"检查可回滚清单":ac==="diff"?"版本比较":ac==="undo"?"预览回滚":"预览回滚";
// list 与 diff 是只读查询，标题不该像"正在回滚"；时间戳只在挑定某个版本（undo）时才加，
// 否则会读成"回滚到某时刻"
const showTs=(ac==="undo");
return {main:label,fname:fp?fp+(showTs&&ts?" to "+ts:""):(showTs&&ts?"to "+ts:"")};}
if(s.indexOf("session_send")>=0){
const tid=String(argGet(args,"target_id")||"").trim().slice(0,12);
return {main:"多Agent协作"+(tid?" · to "+tid:""),fname:""};}
if(s.indexOf("session_multisend")>=0){
const ch=String(argGet(args,"channel")||"").trim();
const tids=argGet(args,"target_ids");
let grp=ch||"";
if(!grp&&Array.isArray(tids)&&tids.length)grp="组"+(tids.length>1?tids.length+"个":"1个");
return {main:"多Agent协作"+(grp?" · to "+grp:""),fname:""};}
const unk='(unknown)';
if(s===unk)return {main:"无法识别的工具（见下方参数）",fname:""};
/* 兜底：拿得到路径就带上文件名。
   提交类工具（`commit_write`）的请求参数里只有 confirm_id，路径靠上面从
   `confirmPathCache` 合并进来；若各工具分支没接管，这里补上，否则标题只有
   工具名、看不出改的是哪个文件。 */
{const p=String(argGet(args,"path")||argGet(args,"dest_path")||argGet(args,"source_path")||"").trim();
if(p){const leaf=pathLeaf(p);if(leaf)return {main:toolZh(script),fname:leaf};}}
return {main:toolZh(script),fname:""};}
