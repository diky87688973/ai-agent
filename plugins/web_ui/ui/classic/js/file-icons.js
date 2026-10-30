/* 文件类型角标；暴露 window.aiAgentFileIcons。 */
(function (w) {
"use strict";
var SVG = {
file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>',
fileText: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>',
sheet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><path d="M8 13h2"/><path d="M14 13h2"/><path d="M8 17h2"/><path d="M14 17h2"/></svg>',
slides: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>',
image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>',
audio: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
video: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/></svg>',
archive: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/></svg>',
binary: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"/><path d="M8.5 2h7"/><path d="M7 16.5h10"/></svg>',
pdf: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><path d="M10 12h4"/><path d="M10 16h4"/></svg>'
};
var MARK = {
txt:"TXT",md:"M",csv:"CSV",json:"{}",yaml:"YML",toml:"TML",ini:"CFG",xml:"XML",lock:"LCK",
html:"<>",css:"#",js:"JS",ts:"TS",tsx:"TSX",jsx:"JSX",vue:"VUE",svelte:"SVEL",
py:"Py",go:"Go",rs:"Rs",java:"Jv",kt:"Kt",cs:"C#",cpp:"C++",c:"C",swift:"Sw",rb:"Rb",php:"PHP",
sh:"SH",lua:"Lua",r:"R",dart:"Dt",sql:"SQL",gql:"GQL",proto:"PBF",
docker:"DKR",make:"MK",gradle:"GRD",npm:"NPM"
};
var SVG_KIND = {file:1,pdf:1,word:1,excel:1,ppt:1,image:1,audio:1,video:1,zip:1,bin:1};
function baseName(path){
var s=String(path||"").replace(/\\/g,"/");
var i=s.lastIndexOf("/");
return i>=0?s.slice(i+1):s;
}
function fileIconKind(path){
var name=baseName(path);
var lower=name.toLowerCase();
if(lower==="dockerfile"||lower===".dockerignore"||lower.endsWith(".dockerfile"))return "docker";
if(lower==="makefile"||lower==="gnumakefile"||lower==="cmakelists.txt")return "make";
if(lower==="package.json")return "npm";
if(lower==="package-lock.json"||lower==="pnpm-lock.yaml"||lower==="yarn.lock"||lower==="cargo.lock"||lower==="poetry.lock"||lower==="composer.lock"||lower==="gemfile.lock")return "lock";
var dot=lower.lastIndexOf(".");
var ext=dot>=0?lower.slice(dot+1):"";
if(!ext)return "file";
if(ext==="txt"||ext==="log"||ext==="text")return "txt";
if(ext==="md"||ext==="mdc"||ext==="markdown"||ext==="rst"||ext==="adoc")return "md";
if(ext==="csv"||ext==="tsv")return "csv";
if(ext==="json"||ext==="jsonc"||ext==="json5")return "json";
if(ext==="yaml"||ext==="yml")return "yaml";
if(ext==="toml")return "toml";
if(ext==="ini"||ext==="cfg"||ext==="conf"||ext==="properties"||ext==="env")return "ini";
if(ext==="xml"||ext==="xsl"||ext==="xsd")return "xml";
if(ext==="html"||ext==="htm"||ext==="xhtml")return "html";
if(ext==="css"||ext==="scss"||ext==="sass"||ext==="less")return "css";
if(ext==="js"||ext==="mjs"||ext==="cjs")return "js";
if(ext==="ts"||ext==="mts"||ext==="cts")return "ts";
if(ext==="tsx")return "tsx";
if(ext==="jsx")return "jsx";
if(ext==="vue")return "vue";
if(ext==="svelte")return "svelte";
if(ext==="py"||ext==="pyw"||ext==="pyi")return "py";
if(ext==="go")return "go";
if(ext==="rs")return "rs";
if(ext==="java")return "java";
if(ext==="kt"||ext==="kts")return "kt";
if(ext==="cs")return "cs";
if(ext==="c"||ext==="h")return "c";
if(ext==="cpp"||ext==="hpp"||ext==="cc"||ext==="cxx"||ext==="hh")return "cpp";
if(ext==="swift")return "swift";
if(ext==="rb"||ext==="erb")return "rb";
if(ext==="php")return "php";
if(ext==="sh"||ext==="bash"||ext==="zsh"||ext==="ps1"||ext==="bat"||ext==="cmd")return "sh";
if(ext==="lua")return "lua";
if(ext==="r")return "r";
if(ext==="dart")return "dart";
if(ext==="sql"||ext==="psql"||ext==="ddl"||ext==="dml")return "sql";
if(ext==="graphql"||ext==="gql")return "gql";
if(ext==="proto")return "proto";
if(ext==="gradle")return "gradle";
if(ext==="pdf")return "pdf";
if(ext==="doc"||ext==="docx"||ext==="rtf"||ext==="odt")return "word";
if(ext==="xls"||ext==="xlsx"||ext==="xlsm"||ext==="ods")return "excel";
if(ext==="ppt"||ext==="pptx"||ext==="odp")return "ppt";
if(ext==="png"||ext==="jpg"||ext==="jpeg"||ext==="gif"||ext==="webp"||ext==="svg"||ext==="ico"||ext==="bmp")return "image";
if(ext==="mp3"||ext==="wav"||ext==="flac"||ext==="ogg"||ext==="m4a")return "audio";
if(ext==="mp4"||ext==="webm"||ext==="mov"||ext==="mkv"||ext==="avi")return "video";
if(ext==="zip"||ext==="7z"||ext==="rar"||ext==="tar"||ext==="gz"||ext==="tgz"||ext==="bz2")return "zip";
if(ext==="exe"||ext==="dll"||ext==="so"||ext==="dylib"||ext==="wasm"||ext==="bin")return "bin";
return "file";
}
function makeFileIconEl(path){
var kind=fileIconKind(path);
var ico=document.createElement("span");
ico.className="file-type-ico file-type-ico--"+kind;
ico.setAttribute("aria-hidden","true");
if(SVG_KIND[kind]){
var key=kind==="word"?"fileText":kind==="excel"?"sheet":kind==="ppt"?"slides":kind==="zip"?"archive":kind==="bin"?"binary":kind==="pdf"?"pdf":kind==="image"?"image":kind==="audio"?"audio":kind==="video"?"video":"file";
ico.innerHTML=SVG[key]||SVG.file;
}else{
ico.textContent=MARK[kind]||"";
}
return ico;
}
function fileIconHtml(path){
var el=makeFileIconEl(path);
return el.outerHTML;
}
w.aiAgentFileIcons={kind:fileIconKind,el:makeFileIconEl,html:fileIconHtml};
})(window);
