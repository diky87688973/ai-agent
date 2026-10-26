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
return {main:"目录快速搜索",fname:leaf+(pat?" · /"+pat+"/":"")};}
if(s.indexOf("find_in_file")>=0){
const path=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(path)||"（未指定 path）";
const occ=argGet(args,"occurrence");
const re=!!argGet(args,"regex");
const o=occ!=null&&occ!==0?" · 第"+(Number(occ)+1)+"处":"";
return {main:"单文件单点定位",fname:leaf+o};}
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
if(s.indexOf("background_task")>=0){
const act=String(argGet(args,"action")||"").toLowerCase();
if(act==="create"){
const label=String(argGet(args,"label")||"").trim();
return {main:"后台任务",fname:label||"（未指定小标题）"};}
if(act==="list"){
const st=String(argGet(args,"status")||"").trim();
const bt=String(argGet(args,"batch")||"").trim();
return {main:"后台任务",fname:"列表"+(bt?" · "+bt:"")+(st?" · "+st:"")};}
if(act==="cancel"){
const tid=String(argGet(args,"task_id")||"").trim();
return {main:"后台任务",fname:"取消 · "+(tid||"?")};}
if(act==="output"){
const tid=String(argGet(args,"task_id")||"").trim();
return {main:"后台任务",fname:"结果 · "+(tid||"?")};}
return {main:"后台任务",fname:act||"?"};}
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
return {main:"用户确认",fname:t||"（无标题）"};}
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
return {main:"通用内容搜索",fname:leaf+(pat?" · /"+pat+"/":"")};}
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
return {main:"正则定位",fname:(tgt||"?")+(pat?" · /"+pat+"/":"")+(glob&&glob!=="*"?" · "+glob:"")};}
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
if(s.indexOf("subagent")>=0){
const ac=String(argGet(args,"action")||"").trim().toLowerCase();
const lab=String(argGet(args,"label")||"").trim();
if(ac==="create")return {main:"创建子智能体",fname:lab||"（未命名任务）"};
if(ac==="send")return {main:"发送给子智能体",fname:lab||String(argGet(args,"child_id")||"").slice(0,8)};
if(ac==="status")return {main:"查询子智能体",fname:String(argGet(args,"child_id")||"").slice(0,8)};
if(ac==="result")return {main:"查询子智能体结果",fname:String(argGet(args,"child_id")||"").slice(0,8)};
if(ac==="list")return {main:"子智能体列表",fname:String(argGet(args,"batch")||"")};
if(s.indexOf("subagent_send")>=0)return {main:"子智能体汇报",fname:""};
}
if(s.indexOf("session_send")>=0){
const tid=String(argGet(args,"target_id")||"").trim().slice(0,12);
return {main:"多Agent协作"+(tid?" · to "+tid:""),fname:""};}
if(s.indexOf("session_multisend")>=0){
const ch=String(argGet(args,"channel")||"").trim();
const tids=argGet(args,"target_ids");
let grp=ch||"";
if(!grp&&Array.isArray(tids)&&tids.length)grp="组"+(tids.length>1?tids.length+"个":"1个");
return {main:"多Agent协作"+(grp?" · to "+grp:""),fname:""};}
const dt=desktopToolTitle(script,args,full,null);
if(dt)return dt;
const unk='(unknown)';
if(s===unk)return {main:"无法识别的工具（见下方参数）",fname:""};
/* 兜底：拿得到路径就带上文件名。
   提交类工具（`commit_write`）的请求参数里只有 confirm_id，路径靠上面从
   `confirmPathCache` 合并进来；若各工具分支没接管，这里补上，否则标题只有
   工具名、看不出改的是哪个文件。 */
{const p=String(argGet(args,"path")||argGet(args,"dest_path")||argGet(args,"source_path")||"").trim();
if(p){const leaf=pathLeaf(p);if(leaf)return {main:toolZh(script),fname:leaf};}}
return {main:toolZh(script),fname:""};}

/* ── Visual Operator：标题后的执行摘要 ─────────────────────────────────────────────
   这四个工具的动作全在参数里，标题只写「看屏 / 鼠标 / 键盘」等于什么都没说：
   用户看不出模型是点哪儿、打什么字、等哪块画面。摘要统一成
   `动作 -> 目标 (位置)`，参数里没有目标时留位置，执行完再用回执里的
   窗口标题 / 命中窗口补一次（`desktopToolTitle(..., data)`）。
   摘要只做展示，不参与任何门控；取不到就退回参数摘要，绝不编造。 */
function desktopToolKind(script){
var s=String(script||"").toLowerCase();
if(s.indexOf("desktop_eye")>=0)return "eye";
if(s.indexOf("desktop_mouse")>=0)return "mouse";
if(s.indexOf("desktop_keyboard")>=0)return "keyboard";
if(s.indexOf("desktop_wait")>=0)return "wait";
if(s.indexOf("task_sleep")>=0)return "sleep";
return "";}
function desktopPointText(args){
var x=argGet(args,"x"),y=argGet(args,"y");
if(x==null||x===""||y==null||y==="")return "";
return "("+x+", "+y+")";}
function desktopRegionText(args){
var x=argGet(args,"x"),y=argGet(args,"y"),w=argGet(args,"width"),h=argGet(args,"height");
if(x==null||x===""||y==null||y===""||w==null||w===""||h==null||h==="")return "";
return "("+x+", "+y+", "+w+"×"+h+")";}
function desktopClipText(text,n){
var s=String(text==null?"":text);
return s.length>n?s.slice(0,n)+"…":s;}
/* 毫秒 → 时长文本：按 秒 / 分 / 时 / 天 展开，不足 10 秒保留一位小数。 */
function desktopDurationText(ms){
var total=Math.max(0,Math.round(Number(ms)||0));
if(total<10000)return (Math.round(total/100)/10)+" 秒";
var rest=Math.round(total/1000);
var days=Math.floor(rest/86400);rest-=days*86400;
var hours=Math.floor(rest/3600);rest-=hours*3600;
var mins=Math.floor(rest/60);rest-=mins*60;
var parts=[];
if(days)parts.push(days+" 天");
if(hours)parts.push(hours+" 小时");
if(mins)parts.push(mins+" 分");
if(rest)parts.push(rest+" 秒");
return parts.length?parts.join(" "):"0 秒";}
function _desktopData(data){
return (data&&typeof data==="object")?data:null;}
/* 取回执里的窗口标题：`desktop_eye` 放在 data.window，鼠标的 `hit` 在顶层或 performed 里。 */
function desktopTargetTitle(data){
var d=_desktopData(data);if(!d)return "";
if(d.window&&typeof d.window==="object"&&d.window.title)return String(d.window.title);
var p=(d.performed&&typeof d.performed==="object")?d.performed:d;
if(p.hit&&typeof p.hit==="object"&&p.hit.title)return String(p.hit.title);
if(d.hit&&typeof d.hit==="object"&&d.hit.title)return String(d.hit.title);
return "";}
function desktopToolTitle(script,args,full,data){
var kind=desktopToolKind(script);if(!kind)return null;
var a=(args&&typeof args==="object")?args:{};
var d=_desktopData(data);
var title=desktopTargetTitle(d);
function cut(text,n){var s=String(text==null?"":text);if(full||s.length<=n)return s;return s.slice(0,n)+"…";}
if(kind==="eye"){
var win=cut(String(argGet(a,"window")||"").trim(),24);
var hwnd=argGet(a,"hwnd");
var where="全屏";
if(title)where="窗口 -> "+cut(title,24);
else if(win)where="窗口 -> "+win;
else if(hwnd!=null&&hwnd!=="")where="窗口 -> hwnd "+hwnd;
else if(d&&d.capture&&d.capture.width!=null)where="局部 -> ("+d.capture.x+", "+d.capture.y+", "+d.capture.width+"×"+d.capture.height+")";
else {var reg=desktopRegionText(a);if(reg)where="局部 -> "+reg;}
var hover=argGet(a,"hover");
if(Array.isArray(hover)&&hover.length===2)where+=" · 悬停 ("+hover[0]+", "+hover[1]+")";
else if(d&&d.hover&&d.hover.x!=null)where+=" · 悬停 ("+d.hover.x+", "+d.hover.y+")";
return {main:"看屏",fname:where};}
if(kind==="mouse"){
var act=String(argGet(a,"action")||"click").toLowerCase();
var pos=desktopPointText(a);
var target=title?cut(title,24):cut(String(argGet(a,"window")||"").trim(),24);
if(act==="cursor")return {main:"鼠标",fname:"查询光标"};
if(act==="move")return {main:"鼠标",fname:"移动 -> "+(pos||"光标处")};
if(act==="drag"){
var tx=argGet(a,"to_x"),ty=argGet(a,"to_y");
return {main:"鼠标",fname:"拖拽 -> "+(pos||"光标处")+" → ("+tx+", "+ty+")"};}
if(act==="scroll"){
var amount=argGet(a,"amount");
return {main:"鼠标",fname:"滚动 "+(amount==null?"":amount)+(pos?" -> "+pos:"")};}
return {main:"鼠标",fname:"点击 -> "+(target?target+" ":"")+(pos||"光标处")};}
if(kind==="keyboard"){
var kact=String(argGet(a,"action")||"type").toLowerCase();
var repeat=argGet(a,"repeat");
var times=(repeat!=null&&Number(repeat)>1)?" ×"+repeat:"";
if(kact==="key")return {main:"键盘",fname:"按键 -> "+cut(String(argGet(a,"key")||""),18)+times};
if(kact==="hotkey")return {main:"键盘",fname:"组合键 -> "+cut(String(argGet(a,"keys")||""),24)+times};
return {main:"键盘",fname:"输入 -> "+cut(String(argGet(a,"text")||""),18)+times};}
if(kind==="wait"){
var until=String(argGet(a,"until")||"change").toLowerCase();
var wtitle=title?cut(title,24):cut(String(argGet(a,"window")||"").trim(),24);
var label=until==="window_appears"?"窗口出现 -> "+(wtitle||"（未指定窗口）")
:until==="window_disappears"?"窗口消失 -> "+(wtitle||"（未指定窗口）"):"画面变化";
if(until!=="window_appears"&&until!=="window_disappears"){
if(wtitle)label+=" -> "+wtitle;
else if(d&&d.capture&&d.capture.width!=null)label+=" -> ("+d.capture.x+", "+d.capture.y+", "+d.capture.width+"×"+d.capture.height+")";
else {var wreg=desktopRegionText(a);if(wreg)label+=" -> "+wreg;}}
if(d&&d.waited_ms!=null)label+=" · "+desktopDurationText(d.waited_ms);
return {main:"等待条件",fname:label};}
var sleepSec=Number(argGet(a,"seconds"));
return {main:"等待",fname:(sleepSec>0?desktopDurationText(sleepSec*1000):"0 秒")};}
function desktopToolSummary(script,args,data){
var t=desktopToolTitle(script,args,true,data);
return t?String(t.fname||""):"";}
/* 步骤卡标题后的摘要位：没有 `.step-fname` 时按需补一个（倒计时要能落到卡上）。 */
function desktopSetStepSummary(stepWrap,text,ensure){
if(!stepWrap)return;
var shown=String(text==null?"":text);
var f=stepWrap.querySelector(".step-fname");
if(!f){
if(!ensure||!shown)return;
var dot=document.createElement("span");dot.textContent=" · ";
stepWrap.appendChild(dot);
f=document.createElement("span");f.className="step-fname";stepWrap.appendChild(f);
}
f.textContent=shown;}
function desktopUpdateStepSummary(tid,script,args,data){
if(!desktopToolKind(script))return;
var text=desktopToolSummary(script,args,data);
if(!text)return;
var card=(typeof findStepCardForToolCall==="function")?findStepCardForToolCall(tid):null;
if(!card)return;
desktopSetStepSummary(card.querySelector(".step-title-wrap"),text,true);}
/* 等待类工具自己数秒：`task_sleep` 数请求的秒数，`desktop_wait` 数超时上限。
   都以截止时间戳算，不靠累加。`desktop_wait` 越过上限还没收到结果，
   就继续往上数「已超时」，直到工具结束。 */
function desktopWaitSeconds(script,args){
var kind=desktopToolKind(script);
if(kind==="sleep"){
var sec=Number(argGet(args,"seconds"));
return sec>0?Math.round(sec):0;}
if(kind==="wait"){
var ms=Number(argGet(args,"timeout_ms")||10000);
return ms>0?Math.ceil(ms/1000):0;}
return 0;}
function desktopWaitTickText(script,args,left,elapsedMs){
var kind=desktopToolKind(script);
var base=desktopToolSummary(script,args,null);
if(kind==="sleep")return "剩余 "+desktopDurationText(left*1000);
if(left>0)return (base?base+" · ":"")+"剩余 "+desktopDurationText(left*1000);
var total=desktopWaitSeconds(script,args);
var over=Math.max(0,elapsedMs-total*1000);
return (base?base+" · ":"")+"已超时 "+Math.max(1,Math.floor(over/1000))+" 秒";}
var _desktopWaitTickers={};
function desktopStopWaitTicker(tid){
var key=String(tid==null?"":tid);if(!key)return;
var entry=_desktopWaitTickers[key];if(!entry)return;
try{clearInterval(entry.timer);}catch(_e){}
delete _desktopWaitTickers[key];}
/* 同一个调用可能在两处显示（步骤卡 + 对话区工具行），两处共用一个计时器：
   第二个登记方只挂自己的刷新函数，不重置截止时间，否则倒计时会被"重启"。 */
function desktopStartWaitTicker(tid,script,args,apply){
var key=String(tid==null?"":tid);if(!key)return;
var kind=desktopToolKind(script);
var total=desktopWaitSeconds(script,args);
if(!total||typeof apply!=="function")return;
function paint(){
var entry=_desktopWaitTickers[key];if(!entry)return;
var now=Date.now();
var leftMs=entry.deadline-now;
var left=leftMs>0?Math.ceil(leftMs/1000):0;
var over=leftMs>0?0:Math.floor(-leftMs/1000)+1;
var step=left>0?left:-over;
if(step===entry.last)return;
entry.last=step;
var elapsed=Math.max(0,now-entry.started);
for(var i=0;i<entry.applys.length;i++){try{entry.applys[i](left,entry.total,elapsed);}catch(_e){}}
/* `desktop_wait` 到点后还要接着数超时，等工具结果来收尾；
   其它等待到点就停在 0。 */
if(kind!=="wait"&&left<=0)desktopStopWaitTicker(key);}
var entry=_desktopWaitTickers[key];
if(!entry){
var now=Date.now();
entry={deadline:now+total*1000,total:total,started:now,applys:[],last:-1,timer:null};
_desktopWaitTickers[key]=entry;
entry.timer=setInterval(paint,200);
}
entry.applys.push(apply);
paint();}
