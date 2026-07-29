const $=(selector,root=document)=>root.querySelector(selector);
const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
const esc=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const tag=(value,tone="")=>`<span class="tag ${tone}">${esc(value)}</span>`;
const zhDate=value=>{
  const match=String(value||"").match(/(\d{4})-(\d{2})-(\d{2})/);
  return match?`${Number(match[1])}年${Number(match[2])}月${Number(match[3])}日`:"日期待核验";
};
const monthDay=value=>{
  const match=String(value||"").match(/\d{4}-(\d{2})-(\d{2})/);
  return match?`${Number(match[1])}月${Number(match[2])}日`:"待核验";
};
const scanLabel=(data,channel)=>{
  const row=data.readiness?.channels?.[channel]||{};
  if(row.ready&&row.status==="no_new")return `已完成扫描，今日无新增（${zhDate(row.scanAsOf)}）`;
  if(row.ready&&row.status==="degraded")return `已完成扫描，来源受限（${zhDate(row.scanAsOf)}）`;
  if(row.ready)return `已完成扫描（${zhDate(row.scanAsOf)}）`;
  return `今日尚未完成扫描`;
};
const external=(url,label)=>url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`:"";
const source=(name,url)=>url
  ?`<p class="source">来源：${external(url,name||"公告原文")}</p>`
  :`<p class="source pending-source">${esc(name||"待补原始来源")}</p>`;
const card=(title,body,label="",href="",date="")=>`<article class="card">${label?tag(label,"gold"):""}${date?`<time>${esc(zhDate(date))}</time>`:""}<h3>${esc(title)}</h3><p>${esc(body)}</p>${href?`<a class="more" href="${esc(href)}">查看详情 →</a>`:""}</article>`;
const cover=(asOf,eyebrow,title,lead,image,extra="",sourceStatus="")=>`<section class="cover" style="--image:url('${image}')"><div class="cover-inner"><p class="eyebrow">${esc(eyebrow)}</p><h1>${esc(title)}</h1><p class="lead">${esc(lead)}</p><div class="cover-date">${esc(zhDate(asOf))}</div><div class="date-status"><span><b>页面日期</b>${esc(zhDate(asOf))}</span><span><b>数据截至</b>${esc(sourceStatus||zhDate(asOf))}</span></div><div class="actions"><a class="btn" href="#today">阅读本期内容</a><button class="btn ghost copy" type="button">复制链接</button></div>${extra}</div></section>`;
const section=(title,sub,body,id="")=>`<section class="section"${id?` id="${id}"`:""}><div class="section-head"><h2>${title}</h2><p>${sub||""}</p></div>${body}</section>`;
const dailyImageArchive=(index,channel)=>{
  const rows=(index?.channels?.[channel]||[])
    .filter(row=>row?.publicPath&&(row.webStatus==="published"||["v1_history","v1_history_corrected"].includes(row.origin)))
    .sort((left,right)=>String(right.date||"").localeCompare(String(left.date||"")));
  const name={listed:"上市公司",private:"证券私募",ma:"收并购",tender:"金融招投标"}[channel]||"栏目";
  if(!rows.length)return section("日图归档",`${name}日图将在首个完整早报发布后归档`,`<div class="compact-status">暂无已发布日图。</div>`,`${channel}-daily-images`);
  const [latest,...history]=rows;
  const groups=[
    ["V2日图期次",history.filter(row=>row.origin==="v2")],
    ["迁移期V1日图",history.filter(row=>row.origin==="v1_daily")],
    ["V1历史期次",history.filter(row=>["v1_history","v1_history_corrected"].includes(row.origin))],
  ].filter(([,items])=>items.length);
  const historyMarkup=groups.map(([label,items])=>{
    const years=[...new Set(items.map(row=>String(row.date||"").slice(0,4)).filter(Boolean))].sort().reverse();
    return `<div class="daily-image-history-group"><b>${esc(label)}</b>${years.map(year=>`<div class="daily-image-year"><span>${esc(year)}年</span><div>${items.filter(row=>String(row.date||"").startsWith(year)).map(row=>`<a href="${esc(row.publicPath)}" target="_blank" rel="noopener noreferrer">${esc(monthDay(row.date))}</a>`).join("")}</div></div>`).join("")}</div>`;
  }).join("");
  const latestLabel=latest.origin==="v2"?"最新V2日图":latest.origin==="v1_daily"?"迁移期V1日图":latest.origin==="v1_history_corrected"?"V1历史期次":"V1历史日图";
  return section("日图归档",`已发布 ${rows.length} 期`, `<div class="daily-image-summary"><a class="daily-image-latest" href="${esc(latest.publicPath)}" target="_blank" rel="noopener noreferrer"><span>${esc(latestLabel)}</span><b>${esc(zhDate(latest.date))}｜${esc(name)}日图</b><small>查看图片 →</small></a>${history.length?`<button class="daily-image-toggle" type="button" data-daily-image-toggle aria-expanded="false">历史日图（${history.length}期）</button>`:""}</div>${history.length?`<div class="daily-image-history" data-daily-image-history hidden>${historyMarkup}</div>`:""}`,`${channel}-daily-images`);
};
const facts=items=>`<div class="facts">${items.map(([key,value])=>`<div><b>${esc(key)}</b>${esc(value||"—")}</div>`).join("")}</div>`;
const splitTitle=value=>{
  const [company,...rest]=String(value||"").split("｜");
  return [company.replace(/^(必看|重点)[｜：]?/,""),rest.join("｜")];
};

function pagedList(rows,{render,pageSize=10,filters=[],rowClass="record-grid"}){
  let page=1;
  const host=document.createElement("div");
  host.innerHTML=`<div class="filters"><input data-q type="search" placeholder="搜索关键词">${filters.map((filter,index)=>`<select data-f="${index}"><option value="">${esc(filter.label)}</option>${[...new Set(rows.map(filter.value).filter(Boolean))].sort().map(value=>`<option>${esc(value)}</option>`).join("")}</select>`).join("")}</div><div class="result-head"><span data-count></span><span>每页 ${pageSize} 条</span></div><div class="${rowClass}" data-rows></div><div class="pager"><button class="btn" data-prev>上一页</button><span data-page></span><button class="btn" data-next>下一页</button></div>`;
  const draw=()=>{
    const query=$("[data-q]",host).value.trim().toLowerCase();
    const selected=$$("select",host).map(element=>element.value);
    const filtered=rows.filter(row=>(!query||JSON.stringify(row).toLowerCase().includes(query))&&filters.every((filter,index)=>!selected[index]||String(filter.value(row))===selected[index]));
    const pageCount=Math.max(1,Math.ceil(filtered.length/pageSize));
    page=Math.min(page,pageCount);
    $("[data-count]",host).textContent=`共 ${filtered.length} 条`;
    $("[data-page]",host).textContent=`${page} / ${pageCount}`;
    $("[data-prev]",host).disabled=page===1;
    $("[data-next]",host).disabled=page===pageCount;
    $("[data-rows]",host).innerHTML=filtered.length?filtered.slice((page-1)*pageSize,page*pageSize).map(render).join(""):`<div class="empty">当前筛选条件下没有记录</div>`;
  };
  $$("input,select",host).forEach(element=>{
    const refresh=()=>{page=1;draw();};
    element.addEventListener("input",refresh);
    element.addEventListener("change",refresh);
  });
  $("[data-prev]",host).onclick=()=>{page--;draw();};
  $("[data-next]",host).onclick=()=>{page++;draw();};
  draw();
  return host;
}

function poolTable(rows,{kind}){
  const host=document.createElement("div");
  const counts=Object.fromEntries(["L1","L2","L3","PF1","PF2"].map(tier=>[tier,rows.filter(row=>row.tier===tier).length]));
  const tiers=kind==="listed"
    ?[["",`全部 ${rows.length}`],["L1",`L1 ${counts.L1}`],["L2",`L2 ${counts.L2}`],["L3",`L3 ${counts.L3}`]]
    :[["",`全部 ${rows.length}`],["PF1",`PF1 ${counts.PF1}`],["PF2",`PF2 ${counts.PF2}`]];
  host.className="embedded-pool";
  host.innerHTML=`<div class="pool-tools"><input type="search" placeholder="搜索名称、代码或关系"><div class="pool-tabs">${tiers.map(([value,label])=>`<button type="button" data-tier="${value}" class="${value===""?"active":""}">${label}</button>`).join("")}</div></div><div class="pool-scroll"><table><thead><tr>${kind==="listed"?"<th>公司</th><th>代码 / 市场</th><th>层级</th><th>陕西关系 / 纳入原因</th>":"<th>管理人</th><th>登记编号</th><th>注册省</th><th>办公省</th><th>层级 / 关系类型</th>"}</tr></thead><tbody></tbody></table></div><p class="pool-count"></p>`;
  let tier="";
  const draw=()=>{
    const query=$("input",host).value.trim().toLowerCase();
    const filtered=rows.filter(row=>(!tier||row.tier===tier)&&(!query||JSON.stringify(row).toLowerCase().includes(query)));
    $("tbody",host).innerHTML=filtered.map(row=>kind==="listed"
      ?`<tr><td><b>${esc(row.name)}</b></td><td>${esc(row.code)} · ${esc(row.exchange)}</td><td>${tag(row.tier)}</td><td>${esc(row.reason)}</td></tr>`
      :`<tr><td><b>${esc(row.name)}</b><small>${esc(row.relationLabel)}</small></td><td>${esc(row.registerNo||"待核验")}</td><td>${esc(row.registerProvince)}</td><td>${esc(row.officeProvince||"待核验")}</td><td>${tag(row.tier,row.tier==="PF2"?"red":"")} ${esc(row.relationLabel)}</td></tr>`).join("");
    $(".pool-count",host).textContent=`当前显示 ${filtered.length} 条；表格内部滚动可查看全部。`;
  };
  $("input",host).addEventListener("input",draw);
  $$("[data-tier]",host).forEach(button=>button.onclick=()=>{
    tier=button.dataset.tier;
    $$("[data-tier]",host).forEach(item=>item.classList.toggle("active",item===button));
    draw();
  });
  draw();
  return host;
}

const businessMeta=row=>{
  const business=row.business||{};
  return `<span class="business-path">${esc(business.category||"综合事项")} · ${esc(business.subcategory||"综合事项")}</span>${business.priority==="focus"?tag("业务重点","green"):""}${business.contentImportance?tag(business.contentImportance,business.contentImportance.includes("必看")||business.contentImportance==="内容重要"?"red":"gold"):""}<span class="targets">关注：${esc((business.targets||["公司公告"]).join("、"))}</span>`;
};
const newsReference=({row,company,title,text})=>`<article class="news-reference"><div><b>${esc(company)}</b><span>${esc(title)}</span><p>${esc(text)}</p></div><a href="#${esc(row.referenceAnchor)}">查看主事项 →</a></article>`;
const newsSources=row=>{
  const rows=(row.sources||[]).filter(item=>item&&item.sourceUrl);
  if(!rows.length&&row.sourceUrl)rows.push({sourceUrl:row.sourceUrl,announcementTitle:row.sourceName||"公告"});
  if(!rows.length)return `<span class="row-source pending-source">待核验</span>`;
  return `<div class="row-sources">${rows.map((item,index)=>`<a class="row-source" href="${esc(item.sourceUrl)}" target="_blank" rel="noopener noreferrer" title="${esc(item.announcementTitle)}">${rows.length>1?`公告${index+1}`:"公告"}</a>`).join("")}</div>`;
};
const newsRow=({row,company,title,text,numbers="",follow=""})=>{
  if(row.isReference)return newsReference({row,company,title,text});
  const detailId=row.canonicalDetailId||row.focusAnchorId||"";
  return `<article class="news-row${detailId?" canonical-detail":""}"${detailId?` id="${esc(detailId)}" tabindex="-1"`:""}><div class="news-company"><b>${esc(company)}</b><span>${esc(title||"")}</span><time>${esc(monthDay(row.publishedAt))}</time></div><div class="news-main"><div class="news-meta">${businessMeta(row)}</div>${numbers?`<div class="news-numbers">${numbers}</div>`:""}<p>${esc(text)}</p>${follow?`<small><b>关注要点：</b>${esc(follow)}</small>`:""}</div>${newsSources(row)}</article>`;
};

function home(data){
  const channels=[
    ["上市公司早报","按公告日期、重要度与公司去重展示当期事项。","上市公司","assets/channel-listed.webp","listed.html"],
    ["证券私募年度库",`${data.private.products.length}只年内新增备案，可按月份、管理人和层级筛选。`,"证券私募","assets/channel-private.webp","private.html"],
    ["收并购年度库",`${data.ma.projects.length}个年度项目，已核验与待补来源分区展示。`,"收并购","assets/channel-ma.webp","ma.html"],
    ["金融招投标",`${data.tender.projects.length}个正式独立项目及${data.tender.pending.length}条待回源观察线索。`,"金融招投标","assets/channel-tender.webp","tender.html"],
    ["国企动态早报",`${zhDate(data.soe.scanAsOf)}已完成扫描；最近有效事件${zhDate(data.soe.latestRecordDate)}。`,"国企动态","assets/channel-soe.png","soe.html"],
  ];
  const featured=data.homeHighlights.map(item=>card(item.title,item.body,item.category,item.href,item.date)).join("");
  const sourceStatus=`${zhDate(data.scanAsOf)}已完成五栏目扫描；各栏最近事件日期见频道页`;
  return cover(data.asOf,"SHAANXI CAPITAL MARKET DAILY","陕西资本市场动态","聚合陕西上市公司、证券私募、收并购、金融招投标及国企资本动态。","channel-soe.png","",sourceStatus)
    +`<div class="wrap">${section("今日重点",zhDate(data.asOf),`<div class="grid">${featured}</div>`,"today")}${section("进入频道","日报与年度项目库",`<div class="channel-grid">${channels.map(channel=>`<article class="card image"><img src="${channel[3]}" alt=""><div>${tag(channel[2],"gold")}<h3>${channel[0]}</h3><p>${channel[1]}</p><a class="more" href="${channel[4]}">进入频道 →</a></div></article>`).join("")}</div>`)}</div>`;
}

function assertHomeHighlightLayout(){
  if(document.body.dataset.page!=="index"||window.innerWidth<861)return;
  const cards=$$("#today .grid .card");
  if(cards.length!==4)throw Error("首页重点卡片数量不是4张");
  const heights=cards.map(item=>Math.round(item.getBoundingClientRect().height));
  if(Math.max(...heights)-Math.min(...heights)>1)throw Error("首页四张重点卡片高度不一致");
  cards.slice(0,2).forEach((item,index)=>{
    const paragraph=$("p",item);
    if(!paragraph||paragraph.scrollHeight>paragraph.clientHeight+1){
      throw Error(`首页第${index+1}张上市公司卡片正文发生视觉省略`);
    }
  });
  document.body.dataset.homeLayoutVerified="true";
}

function listed(data){
  const daily=data.listed.daily;
  const host=document.createElement("div");
  const fixed=(daily.fixed_columns||[]).flatMap(group=>(group.items||[]).map(item=>({...item,group:group.title})));
  const focusCompanies=data.listed.focusCompanies||[];
  const focusTags=data.listed.businessTaxonomy?.focusTags||[];
  const focusTagRows=[
    ["section-01",daily.opportunities||[]],
    ["section-02",daily.risk_rows||[]],
    ["section-03",daily.tiles||[]],
    ["section-04",daily.capital_rows||[]],
    ["section-05",fixed],
  ].flatMap(([sectionId,rows])=>rows.map((row,index)=>{
    if(!row.isReference&&row.business?.priority==="focus"&&!row.canonicalDetailId){
      row.focusAnchorId=`listed-focus-${sectionId}-${index+1}`;
    }
    return row;
  })).filter(row=>!row.isReference&&row.business?.priority==="focus");
  const focusTagLinks=focusTags.map(item=>{
    const hits=focusTagRows.filter(row=>row.business?.category===item.category&&row.business?.subcategory===item.name);
    const hit=hits.find(row=>row.canonicalDetailId)||hits[0];
    const companies=[...new Set(hits.map(row=>row.company||splitTitle(row.title)[0]).filter(Boolean))];
    const anchor=hit?.canonicalDetailId||hit?.focusAnchorId||hit?.referenceAnchor||"";
    const label=`${item.category} · ${item.name}`;
    return hit&&anchor
      ?`<a class="focus-tag hit" href="#${esc(anchor)}" title="今日命中：${esc(companies.join("、"))}" aria-label="${esc(label)}，今日命中${esc(companies.join("、"))}，点击查看主事项">${esc(label)}</a>`
      :`<span class="focus-tag">${esc(label)}</span>`;
  }).join("");
  const block=(id,no,title,rows,render)=>`<section class="dense-section" id="${id}"><header><h2><span>${no}</span>${title}</h2><b>${rows.length}条</b></header><div class="news-list">${rows.map(render).join("")||`<div class="compact-empty">本期无新增事项。</div>`}</div></section>`;
  const body=
    block("section-01","01","今日业务机会",daily.opportunities,row=>{const [,company]=row.title.split("｜");return newsRow({row,company,title:"业务机会",text:row.body});})
    +block("section-02","02","重大事项与风险公告",daily.risk_rows,row=>newsRow({row,company:row.company,title:row.tag,text:row.event}))
    +block("section-03","03","上市公司动态",daily.tiles,row=>{const [company,type]=splitTitle(row.title);return newsRow({row,company,title:type,text:row.body});})
    +block("section-04","04","股东变动与资本运作",daily.capital_rows,row=>newsRow({row,company:row.company,title:"资本运作",numbers:row.numbersHtml,text:row.attention}))
    +block("section-05","05","股东会、治理与固定披露清单",fixed,row=>{const [company,type]=splitTitle(row.title);return newsRow({row,company,title:type||row.group,text:row.body});})
    +block("section-06","06","今日重点跟踪公司",daily.follow_items||[],row=>newsRow({row,company:row.company,title:row.businessSubcategory,text:row.whyImportant}));
  const nav=[["business-focus","重点跟踪"],["section-01","01 机会"],["section-02","02 风险"],["section-03","03 动态"],["section-04","04 资本运作"],["section-05","05 治理披露"],["section-06","06 下一步"],["listed-pool","上市观察池"],["listed-daily-images","日图归档"],["listed-archive","历史正文"]];
  const archive=data.listed.archive.slice(0,24).map((item,index)=>`<a ${index>=8?'class="archive-more" hidden':""} href="${esc(item.href)}">${esc(zhDate(item.date))}</a>`).join("");
  const evidence=(daily.sourceEvidence||[]).map(row=>`<li><span>${esc(row.company)}｜${esc(row.title)}</span>${external(row.sourceUrl,"公告原文")}</li>`).join("");
  host.innerHTML=cover(data.asOf,"DAILY ISSUE · LISTED","陕西上市公司早报","重点跟踪置顶，01—06栏目保持紧凑阅读；重复事项链接到唯一主记录。","channel-listed.webp","",`${scanLabel(data,"listed")}；最近公告 ${zhDate(data.listed.latestEventDate)}`)
    +`<div class="listed-shell"><aside class="page-toc">${nav.map(([id,label])=>`<a href="#${id}">${label}</a>`).join("")}</aside><div class="listed-content">${section("今日概览",`数据更新至${zhDate(data.asOf)}`,`<div class="dense-kpis">${daily.kpis.map((item,index)=>`<div><b>${esc(item.num)}</b><span>${["检索公告","发布公司","精选事项","待核验候选"][index]}</span></div>`).join("")}</div>`,"today")}<section class="dense-section focus-board" id="business-focus"><header><h2>业务重点 · 今日重点跟踪</h2><b>${focusTags.length}个标签 · ${focusCompanies.length}家公司</b></header><p>${esc(data.listed.businessTaxonomy?.priorityMeaning||"业务重点用于客户跟进优先级。")} 固定展示21个二级标签；绿色为今日命中，点击可直达主事项。</p><div class="focus-tags" aria-label="上市公司二级业务重点标签">${focusTagLinks}</div><div class="focus-hit-list">${focusCompanies.map(item=>`<a class="focus-company-link" href="#${esc(item.anchorId)}"><b>${esc(item.company)}</b><span>${esc(item.business.category)} · ${esc(item.business.subcategory)}</span><small>${esc(item.followText)}</small></a>`).join("")}</div></section><div class="daily-sections">${body}</div><section class="listed-evidence-archive"><button type="button" data-listed-evidence-toggle aria-expanded="false">官方公告证据档案（${daily.sourceEvidence?.length||0}条，默认收起）</button><div data-listed-evidence hidden><p>完整公告仅用于追溯，不作为客户摘要直接展示。</p><ul>${evidence}</ul></div></section><section class="dense-section" id="listed-pool"><header><h2>上市公司观察池</h2><b>${data.listed.counts.total} = ${data.listed.counts.L1} + ${data.listed.counts.L2} + ${data.listed.counts.L3}</b></header><p class="pool-definition">L1为陕西辖区A股；L2为陕西办公或经营的境外上市主体；L3为陕西实质强关联上市公司。</p><div data-listed-pool></div></section>${dailyImageArchive(data.dailyImageArchive,"listed")}<section class="dense-section" id="listed-archive"><header><h2>历史早报正文</h2><b>已发布期次</b></header><div class="archive">${archive}</div><button class="archive-toggle" type="button" data-archive-toggle>查看更多日期</button></section></div></div>`;
  $("[data-listed-pool]",host).replaceWith(poolTable(data.listed.entities,{kind:"listed"}));
  return host;
}

function privatePage(data){
  const channel=data.private;
  const host=document.createElement("div");
  const months=Object.keys(channel.annualMonthCounts).sort().reverse();
  const managerCount=new Set(channel.products.map(row=>row.managerName)).size;
  const chronological=[...months].reverse();
  const zeroMonths=chronological.filter(key=>channel.annualMonthCounts[key]===0).map(key=>`${Number(key.slice(5))}月`);
  const nonzeroMonths=chronological.filter(key=>channel.annualMonthCounts[key]>0).map(key=>`${Number(key.slice(5))}月${channel.annualMonthCounts[key]}只`);
  host.innerHTML=cover(data.asOf,"ANNUAL DATABASE · PRIVATE FUND","陕西证券私募年度库","年度备案按月检索；产品统计与管理人观察池分别呈现。","channel-private.webp","",`${scanLabel(data,"private")}；最近备案 ${zhDate(channel.latestEventDate)}`)
    +`<div class="wrap compact-wrap">${section("年度概览",`${data.year}年1月1日至${zhDate(data.asOf)}`,`<div class="private-summary"><div><b>${channel.products.length}只</b><span>年内新增备案产品</span></div><div><b>${managerCount}家</b><span>涉及管理人</span></div><div><b>${channel.managerCounts.total}家</b><span>管理人观察池：PF1 ${channel.managerCounts.PF1} + PF2 ${channel.managerCounts.PF2}</span></div></div><div class="month-strip">${chronological.map(key=>`<div><b>${Number(key.slice(5))}月</b><span>${channel.annualMonthCounts[key]}只</span></div>`).join("")}</div><p class="scan-note">截至${zhDate(channel.sourceAsOf)}，${zeroMonths.length?`${zeroMonths.join("、")}未识别新增备案；`:""}${nonzeroMonths.join("、")}。</p>`,"today")}<section class="dense-section"><header><h2>年度备案明细</h2><b>全年 ${channel.products.length} 只</b></header><div data-private-products></div></section><section class="dense-section" id="private-pool"><header><h2>证券私募观察池</h2><b>${channel.managerCounts.total} = PF1 ${channel.managerCounts.PF1} + PF2 ${channel.managerCounts.PF2}</b></header><p class="pool-definition">PF1包括陕西注册或外省注册、陕西办公的管理人；PF2包括实质经营、股权关系和协会会员观察。协会会员关系不代表陕西注册或办公。</p><div data-private-pool></div></section><section class="dense-section" id="custodian-ranking"><header><h2>年度产品托管券商统计</h2><b>合计 ${channel.custodianStats.reduce((sum,row)=>sum+row.count,0)} 次</b></header><p class="pool-definition">口径为${data.year}年新增备案产品的公示托管人次数，不等同全部业务合作。</p><div class="custodian-ranking">${channel.custodianStats.map((row,index)=>`<div class="custodian-row${index>=8?" custodian-extra":""}"${index>=8?" hidden":""}><span>${esc(row.label)}</span><i style="--value:${row.count};--max:${channel.custodianStats[0].count}"></i><b>${row.count}</b></div>`).join("")}</div>${channel.custodianStats.length>8?`<button class="archive-toggle" type="button" data-custodian-toggle>展开全部</button>`:""}</section>${dailyImageArchive(data.dailyImageArchive,"private")}</div>`;

  const productsHost=document.createElement("div");
  productsHost.className="private-products";
  productsHost.innerHTML=`<div class="compact-tools private-filter-tools"><input type="search" placeholder="搜索基金、管理人、托管人或编号"><select data-month><option value="">全部月份</option>${months.map(month=>`<option value="${month}">${Number(month.slice(5))}月</option>`).join("")}</select><select data-manager><option value="">全部管理人</option>${[...new Set(channel.products.map(row=>row.managerName))].sort().map(value=>`<option>${esc(value)}</option>`).join("")}</select><select data-tier><option value="">全部层级</option><option>PF1</option><option>PF2</option></select><button type="button" data-reset>重置筛选</button></div><div data-month-groups></div>`;
  const openMonths=new Set(months.slice(0,1));
  const drawProducts=()=>{
    const query=$("input",productsHost).value.trim().toLowerCase();
    const month=$("[data-month]",productsHost).value;
    const manager=$("[data-manager]",productsHost).value;
    const tier=$("[data-tier]",productsHost).value;
    const filtered=channel.products.filter(row=>(!query||JSON.stringify(row).toLowerCase().includes(query))&&(!month||row.filingDate.startsWith(month))&&(!manager||row.managerName===manager)&&(!tier||row.universeTier===tier));
    const active=Boolean(query||month||manager||tier);
    if(active)months.forEach(value=>{if(filtered.some(row=>row.filingDate.startsWith(value)))openMonths.add(value);});
    $("[data-month-groups]",productsHost).innerHTML=months.filter(value=>!month||value===month).map(value=>{
      const rows=filtered.filter(row=>row.filingDate.startsWith(value));
      const isOpen=openMonths.has(value);
      const panelId=`month-panel-${value}`;
      return `<section class="month-group${rows.length?"":" zero-month"}" data-month-group="${value}"><button class="month-toggle" type="button" aria-expanded="${isOpen}" aria-controls="${panelId}"><span><b>${Number(value.slice(5))}月</b><small>${channel.annualMonthCounts[value]}只</small></span><em aria-hidden="true">${isOpen?"收起":"展开"}</em></button><div id="${panelId}" class="month-panel"${isOpen?"":" hidden"}>${rows.length?`<div class="fund-list">${rows.map(row=>`<article class="fund-row" id="fund-${esc(row.fundNo)}"><time>${esc(monthDay(row.filingDate))}<small>备案</small></time><div class="fund-title">${tag(row.universeTier,row.universeTier==="PF2"?"red":"")}<b>${esc(row.fundName)}</b><span>${esc(row.managerName)}</span><small>${esc(row.relationLabel||"关系待核验")}</small></div><div class="fund-meta"><span><b>成立日期</b>${esc(zhDate(row.establishDate))}</span><span><b>托管人</b>${esc(row.custodianLabel||row.custodian)}</span><span><b>基金编号</b>${esc(row.fundNo)}</span></div>${external(row.sourceUrl,"AMAC来源")}</article>`).join("")}</div>`:`<div class="month-empty">截至${zhDate(data.asOf)}，本月未识别新增备案。</div>`}</div></section>`;
    }).join("");
    $$(".month-toggle",productsHost).forEach(button=>button.onclick=()=>{
      const value=button.closest("[data-month-group]").dataset.monthGroup;
      openMonths.has(value)?openMonths.delete(value):openMonths.add(value);
      drawProducts();
    });
  };
  $$("input,select",productsHost).forEach(element=>{
    element.addEventListener("input",drawProducts);
    element.addEventListener("change",drawProducts);
  });
  $("[data-reset]",productsHost).onclick=()=>{
    $("input",productsHost).value="";
    $$("select",productsHost).forEach(element=>element.value="");
    openMonths.clear();
    openMonths.add("2026-07");
    drawProducts();
  };
  drawProducts();
  $("[data-private-products]",host).replaceWith(productsHost);
  $("[data-private-pool]",host).replaceWith(poolTable(channel.managers,{kind:"private"}));
  return host;
}

const maProject=row=>`<article class="ma-row${row.sourceVerified?"":" pending-row"}" id="${esc(row.id)}"><div class="ma-date"><time>${esc(zhDate(row.eventDate||row.reportedDate))}</time>${tag(row.stageText,row.sourceVerified?"gold":"")}</div><div class="ma-main"><h3>${esc(row.title)}</h3><p><b>${esc(row.subject)}</b> · ${esc(row.industry||"行业未标注")}</p><small><b>事实：</b>${esc(row.fact)}；${esc(row.amount)}</small>${row.importance?`<small><b>为什么重要：</b>${esc(row.importance)}</small>`:""}${row.nextStep?`<small><b>关注要点：</b>${esc(row.nextStep)}</small>`:""}${row.plannedNextDate?`<small class="planned"><b>计划节点（待后续公告确认）：</b>${esc(zhDate(row.plannedNextDate))} ${esc(row.plannedNextLabel)}</small>`:""}</div><div class="ma-amount">${row.sourceUrl?external(row.sourceUrl,row.sourceName):`<span class="pending-source">待补原始来源</span>`}</div></article>`;

function maPage(data){
  const channel=data.ma;
  const industryCount=new Set(channel.projects.map(row=>row.industry).filter(Boolean)).size;
  const host=document.createElement("div");
  host.innerHTML=cover(data.asOf,"ANNUAL DATABASE · M&A","陕西收并购年度库","已核验项目与待补原始来源项目分区展示；计划节点不作为已发生进展。","channel-ma.webp","",`${scanLabel(data,"ma")}；最近事件 ${zhDate(channel.sourceAsOf)}`)
    +`<div class="wrap compact-wrap">${section("年度概览",`最近事件${zhDate(channel.sourceAsOf)}，扫描完成${zhDate(channel.scanAsOf)}`,`<div class="dense-kpis"><div><b>${channel.projects.length}个</b><span>年度项目</span></div><div><b>${channel.verifiedProjects.length}个</b><span>已核验原始来源</span></div><div><b>${channel.pendingProjects.length}个</b><span>历史待补原文</span></div><div><b>${industryCount}个</b><span>已标注行业</span></div></div>`,"today")}<div data-verified></div><div data-pending></div>${dailyImageArchive(data.dailyImageArchive,"ma")}${section("口径说明","事实与计划节点分开",`<div class="definition">最近进展日期仅取可访问原始来源确认的公告或实际进展日期。未来付款、股东会和交割安排单列为计划节点，不参与“最新”排序；历史待核验项目不进入首页重点。</div>`)}</div>`;
  const verified=pagedList(channel.verifiedProjects,{pageSize:10,rowClass:"dense-list",filters:[{label:"全部月份",value:row=>row.eventDate.slice(0,7)},{label:"全部主体类型",value:row=>row.dimension},{label:"全部阶段",value:row=>row.stageText}],render:maProject});
  const verifiedSection=$("[data-verified]",host);
  verifiedSection.className="section";
  verifiedSection.removeAttribute("data-verified");
  verifiedSection.innerHTML=`<div class="section-head"><h2>已核验项目</h2><p>按最近公开确认日期倒序</p></div>`;
  verifiedSection.append(verified);
  const pending=pagedList(channel.pendingProjects,{pageSize:10,rowClass:"dense-list",filters:[{label:"全部主体类型",value:row=>row.dimension},{label:"全部阶段",value:row=>row.stageText}],render:maProject});
  const pendingSection=$("[data-pending]",host);
  pendingSection.className="section";
  pendingSection.removeAttribute("data-pending");
  pendingSection.innerHTML=`<div class="section-head"><h2>待补原始来源</h2><p>保留年度线索，不进入首页重点</p></div>`;
  pendingSection.append(pending);
  return host;
}

const tenderUnits=units=>units.length?`<ul class="tender-results">${units.map(unit=>`<li><b>${esc(unit.section||unit.rank||"结果")}</b><span>${esc(unit.name)}</span><em>${esc(unit.quote||"报价未披露")}</em></li>`).join("")}</ul>`:`<p class="pending-source">中标或入围机构待核验</p>`;
const tenderProject=row=>`<article class="tender-row"><div><time>${esc(zhDate(row.latestProgressDate))}</time>${tag(row.statusGroup,row.statusGroup==="已出结果"?"green":"gold")}</div><div><h3>${esc(row.title)}</h3><p class="formal-title">${esc(row.formalTitle)}</p><p><b>${esc(row.purchaser)}</b> · ${esc(row.opportunityType)}</p><small><b>规模：</b>${esc(row.projectScale)}</small><small><b>阶段：</b>${esc(row.stage)}${row.deadlineOrOpening?` · 截止/开标 ${esc(row.deadlineOrOpening)}`:""}</small>${tenderUnits(row.winningOrCandidateUnits)}</div><div>${row.sourceUrl?external(row.sourceUrl,row.sourceName):`<span class="pending-source">待回源</span>`}</div></article>`;

function tender(data){
  const channel=data.tender;
  const byGroup=group=>channel.projects.filter(row=>row.statusGroup===group);
  const renderGroup=(title,rows,emptyText)=>section(title,`${rows.length}个独立项目`,rows.length?`<div class="tender-projects">${rows.map(tenderProject).join("")}</div>`:`<div class="compact-status">${emptyText}</div>`);
  return cover(data.asOf,"DAILY UPDATE · TENDER","陕西金融招投标日报","当前机会、推进项目、已出结果项目与待回源线索分别呈现。","channel-tender.webp","",`${scanLabel(data,"tender")}；最近事件 ${zhDate(channel.sourceAsOf)}`)
    +`<div class="wrap compact-wrap">${section("年度覆盖概览","同一项目不同阶段不重复计项",`<div class="dense-kpis"><div><b>${channel.projects.length}个</b><span>正式独立项目</span></div><div><b>${channel.pending.length}条</b><span>待回源观察</span></div><div><b>${byGroup("已出结果").length}个</b><span>已出结果</span></div><div><b>${channel.projects.length} + ${channel.pending.length}</b><span>正式项目 + 观察线索</span></div></div>`,"today")}${renderGroup("今日可参与机会",byGroup("今日可参与机会"),`截至${zhDate(data.asOf)}，已完成扫描，未识别处于有效报名窗口的新增项目。`)}${renderGroup("正在推进",byGroup("正在推进"),"当前没有仍在推进且尚未出结果的正式项目。")}${renderGroup("已出结果",byGroup("已出结果"),"暂无结果项目。")}${section("待回源观察",`${channel.pending.length}条，不计入${channel.projects.length}个正式项目`, `<div class="tender-projects">${channel.pending.map(tenderProject).join("")}</div>`)}${dailyImageArchive(data.dailyImageArchive,"tender")}</div>`;
}

function soe(data){
  const channel=data.soe;
  const lead=channel.eventOnScanDate
    ?`${zhDate(channel.scanAsOf)}扫描发现当日有效事项，以下按公开日期倒序展示。`
    :`${zhDate(channel.scanAsOf)}已完成扫描，当日未识别新增；以下保留最近有效事件，日期不作当天处理。`;
  const row=item=>`<article class="soe-row"><div><time>${esc(monthDay(item.publishedAt))}</time>${tag(item.category,"gold")}</div><div><b>${esc(item.title)}</b><span>${esc((item.entities||[]).join("、"))}</span></div>${external(item.sourceUrl,item.sourceName||"原文")}</article>`;
  const columns=channel.categoryOrder.map(category=>`<section class="soe-column"><header><h3>${esc(category)}</h3><b>${channel.categoryRecords[category].length}条</b></header><div>${channel.categoryRecords[category].map(row).join("")||`<p class="compact-empty">暂无可核验记录。</p>`}</div></section>`).join("");
  return cover(data.asOf,"DAILY ISSUE · SOE","陕西国企动态早报","资本金融、项目资产、风险治理、产业经营与综合动态并列呈现。","channel-soe.png","",`${scanLabel(data,"soe")}；最近事件 ${zhDate(channel.sourceAsOf)}`)
    +`<div class="wrap compact-wrap">${section("本期重点",lead,`<div class="soe-focus-list">${channel.focusRecords.map(row).join("")}</div>`,"today")}${section("分类动态","每栏按官方公开日期倒序，最多展示最近5条",`<div class="soe-category-grid">${columns}</div>`)}${section("扫描状态",`${zhDate(channel.scanAsOf)}已完成`,`<div class="compact-status">${channel.eventOnScanDate?`本次扫描识别到当日有效事项。`:`今日未识别新增有效事项；最近有效事件为${zhDate(channel.latestRecordDate)}。`} 当前事件库共${channel.recordCount}条，所有展示事项均保留原始来源链接。</div>`)}${section("历史数据边界","较早期次待继续补充",`<div class="callout">${esc(channel.customerBoundary)}</div>`)}</div>`;
}

async function main(){
  const declaredBuildVersion=document.body.dataset.buildVersion;
  // GitHub Pages may briefly serve a browser-cached HTML shell after a new
  // production release.  Probe the tiny version manifest with a unique URL;
  // when the shell is stale, move to a versioned document URL before loading
  // the large data snapshot.  This prevents an old page shell from presenting
  // yesterday's data as if it were today's issue.
  const probe=await fetch(`data/build-version.json?probe=${Date.now()}`,{cache:"no-store"});
  if(!probe.ok)throw Error("构建版本校验失败");
  const activeBuildVersion=String((await probe.json()).buildVersion||"");
  if(!activeBuildVersion)throw Error("构建版本缺失");
  const currentVersion=new URL(location.href).searchParams.get("v");
  if(activeBuildVersion!==declaredBuildVersion&&currentVersion!==activeBuildVersion){
    const current=new URL(location.href);
    current.searchParams.set("v",activeBuildVersion);
    location.replace(current.toString());
    return;
  }
  const response=await fetch(`data/production-data.json?v=${encodeURIComponent(activeBuildVersion)}`,{cache:"no-store"});
  if(!response.ok)throw Error("数据加载失败");
  const data=await response.json();
  try{
    const archiveResponse=await fetch(`data/daily-image-archive.json?v=${encodeURIComponent(activeBuildVersion)}`,{cache:"no-store"});
    data.dailyImageArchive=archiveResponse.ok?await archiveResponse.json():{channels:{}};
  }catch(_error){data.dailyImageArchive={channels:{}};}
  if(data.build.version!==activeBuildVersion)throw Error("页面资源版本不一致，请刷新后重试");
  const renderers={index:home,listed,private:privatePage,ma:maPage,tender,soe};
  const content=renderers[document.body.dataset.page](data);
  const app=$("#app");
  typeof content==="string"?app.innerHTML=content:app.replaceChildren(content);
  assertHomeHighlightLayout();
  $$(".copy").forEach(button=>button.onclick=async()=>{
    await navigator.clipboard.writeText(location.href);
    const old=button.textContent;
    button.textContent="已复制";
    setTimeout(()=>button.textContent=old,1200);
  });
  $$(".focus-company-link").forEach(link=>link.addEventListener("click",()=>requestAnimationFrame(()=>$(link.getAttribute("href"))?.focus({preventScroll:true}))));
  const listedEvidenceToggle=$("[data-listed-evidence-toggle]");
  if(listedEvidenceToggle)listedEvidenceToggle.onclick=()=>{
    const panel=$("[data-listed-evidence]");
    const reveal=panel.hidden;
    panel.hidden=!reveal;
    listedEvidenceToggle.setAttribute("aria-expanded",String(reveal));
    listedEvidenceToggle.textContent=reveal?"收起官方公告证据档案":"官方公告证据档案（默认收起）";
  };
  const archiveToggle=$("[data-archive-toggle]");
  if(archiveToggle)archiveToggle.onclick=()=>{
    const reveal=$$(".archive-more").some(item=>item.hidden);
    $$(".archive-more").forEach(item=>item.hidden=!reveal);
    archiveToggle.textContent=reveal?"收起更多日期":"查看更多日期";
  };
  $$('[data-daily-image-toggle]').forEach(button=>button.onclick=()=>{
    const history=button.parentElement?.parentElement?.querySelector('[data-daily-image-history]');
    if(!history)return;
    const reveal=history.hidden;
    history.hidden=!reveal;
    button.setAttribute("aria-expanded",String(reveal));
    button.textContent=reveal?"收起历史日图":`历史日图（${history.querySelectorAll("a").length}期）`;
  });
  const custodianToggle=$("[data-custodian-toggle]");
  if(custodianToggle)custodianToggle.onclick=()=>{
    const reveal=$$(".custodian-extra").some(item=>item.hidden);
    $$(".custodian-extra").forEach(item=>item.hidden=!reveal);
    custodianToggle.textContent=reveal?"收起":"展开全部";
  };
  $(".nav-toggle").onclick=()=>$(".site-head nav").classList.toggle("open");
}

main().catch(error=>{
  $("#app").innerHTML=`<div class="wrap"><div class="callout">页面载入失败：${esc(error.message)}。</div></div>`;
  console.error(error);
});
