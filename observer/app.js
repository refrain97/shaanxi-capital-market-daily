(() => {
  'use strict';
  const D = window.PROTOTYPE;
  if (!D) { document.querySelector('#main').innerHTML = '<p class="empty-state">素材未能加载，请保持 index.html、data.js、app.js 和 styles.css 在同一目录。</p>'; return; }
  const real = D.meta.prototype === false;
  const production = real && D.meta.production;
  const publicOutput = D.meta.publicOutput === true;
  const storageKey = real ? 'sx-real-reading' : 'sx-prototype-reading';
  const sampleLabel = production ? (production.status==='public'?'每日观察':'本期预览 · 未公开') : real ? '真实资料 · 待验收' : '原型示例';
  const objects = new Map(D.objects.map(o => [o.id, o]));
  const readingPolicy = D.meta.readingPolicy;
  const updates = D.events.flatMap(event => event.updates.map(u => {
    const policy=readingPolicy?.updates?.[u.id];
    return {...u,event,object:objects.get(event.objectId),reading:policy,
      ...(policy?{important:policy.level==='deep',depth:policy.level,summary:policy.summary||u.summary}:{})};
  })).sort((a,b) => `${b.date} ${b.time}`.localeCompare(`${a.date} ${a.time}`));
  const readable = u => !D.meta.contentHolds?.[u.id] && !D.meta.supersededUpdates?.[u.id];
  const byUpdate = new Map(updates.map(u => [u.id,u]));
  const dates = [...new Set(updates.map(u => u.date))];
  const types = {listed:'上市公司', private:'证券私募', platform:'大型平台', enterprise:real?'融资企业':'未上市企业'};
  const relationText = o => publicOutput ? (o.publicRelation || '尚无可公开的陕西关联核实说明') : real && o.type==='private' ? (o.publicRelation || '用户观察池选样对象；陕西关联原因本轮未核实') : o.relation;
  const views = {
    home:{title:'综合动态',description:'客户动态 · 资本脉络'},
    listed:{title:'上市公司'},
    private:{title:'证券私募'},
    platform:{title:'大型平台'},
    mergers:{title:'并购观察'},
    equity:{title:'股权融资'},
    history:{title:'历史回看'},
    share:{title:production?'每日综合精选':real?'样稿精选':'每日综合精选'},
    review:{title:'发现与核查记录'}
  };
  let stored = {};
  try { stored = JSON.parse(sessionStorage.getItem(storageKey) || '{}'); } catch {}
  const state = {pages:stored.pages || {},opened:new Set(stored.opened || []),versions:new Set(),search:''};
  const main = document.querySelector('#main');
  let currentKey = location.hash.slice(1) || 'home';
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  const esc = str => String(str ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const fmt = date => /^\d{4}-\d{2}-\d{2}$/.test(date || '') ? date.replaceAll('-','.') : esc(date);
  const timeText = value => esc(String(value || '未记录').replace('T',' ').replace(/\+08:00$/,' 北京时间'));
  function cutoffHTML(value) {
    const research=value.researchCutoff || value.cutoff;
    const discovery=value.sourceDiscoveryCutoff;
    const label=value.researchCutoff || discovery?'研究截止':'资料截止';
    return `${label} ${timeText(research)}${discovery&&discovery!==research?`<br>发现查询基准 ${timeText(discovery)}（来源按日查询；不代表已覆盖至研究时刻）`:''}`;
  }
  const objectName = u => u.objectNameAtDisclosure || u.object.name;
  const displayTitle = (u,value=u.title) => { const text=String(value||''),name=objectName(u); return text.startsWith(name)?text.slice(name.length).replace(/^[\s｜|：:]+/,'')||text:text; };
  const updateLabel = u => real && production ? (u.production ? (u.publishedAt||publicOutput&&production.status==='public'?'已发布内容':'本期已核查 · 未公开') : '历史真实样稿') : sampleLabel;
  const editionKey = e => e.id || e.date;
  const assetHref = value => typeof value==='string' && !/^\s*(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(value) ? value : /^https?:\/\//.test(value || '') ? value : '';
  const rich = str => esc(str).replace(/(\d[\d,.]*(?:亿元|万元|万股|个月|%))/g,'<strong>$1</strong>');
  const chevron = '<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true"><path d="m2 4 4 4 4-4"/></svg>';
  const route = () => { const [path, query] = currentKey.split('?'); const [page, value] = path.split('/'); return {page, value:decodeURIComponent(value || ''), query:new URLSearchParams(query || '')}; };
  const pageState = () => state.pages[currentKey] ||= {filter:'全部',tab:'recent',scroll:0,query:''};
  function persist() { try { sessionStorage.setItem(storageKey,JSON.stringify({pages:state.pages,opened:[...state.opened]})); } catch {} }
  function navigate(key) { if (key === currentKey) return; pageState().scroll = window.scrollY; persist(); location.hash = key; }
  function heading(config, aside = '') { return `<section class="page-heading${config.object?' object-heading':''}"><div class="heading-main"><h1>${config.title}</h1>${config.description?`<p class="page-description">${config.description}</p>`:''}</div>${aside}</section>`; }
  function coverageText(note) {
    const labels={evidence_hold:'证据不足暂缓',pending_evidence:'待补取资料',processing_incomplete:'处理尚未完成',pending_research:'待补充研究',pending_quality:'待独立内容核查',quality_hold:'内容核查未通过',identity_hold:'对象身份待核实',content_qualified:'内容核查通过',local_ready:'已接入网页',unprocessed:'待处理',triage_incomplete:'事项归并尚未完成'};
    const readable=String(note).replace(/事项状态\s*\{([^{}]*)\}/g,(original,body)=>{
      const rows=body.split(',').map(part=>part.trim().match(/^(['"])([a-z_]+)\1\s*:\s*(\d+)$/));
      if(rows.some(row=>!row||!Object.prototype.hasOwnProperty.call(labels,row[2]))) return original;
      return '事项处理情况：'+rows.map(row=>labels[row[2]]+row[3]+'项').join('、');
    });
    // These older labels describe drafting status, not the committed edition's image availability.
    return readable.replace(/\d+项(?:内容合格待生成|已生成本地成品)(?:[、，]\s*\d+项(?:内容合格待生成|已生成本地成品))*/g,part=>`${[...part.matchAll(/\d+/g)].reduce((sum,row)=>sum+Number(row[0]),0)}项已核查合格`);
  }
  function currentEditionText() {
    const news=D.editions.find(e=>e.presentation==='business-news-20261015');
    if(news)return `业务快讯已导出${news.images?.length||0}张PNG${D.meta.shareDesign?.accepted?'。':' · 新版式待验收。'}`;
    if(readingPolicy?.imagesStatus==='design_pending') return '本轮图片样式待确认；历史PNG保留。';
    if(!production || !['preview','public'].includes(production.status)) return '';
    const edition=D.editions.find(e=>e.id===production.id);
    const ids=production.updateIds || edition?.updateIds;
    if(!edition || !Array.isArray(ids) || !ids.length || new Set(ids).size!==ids.length || !ids.every(id=>byUpdate.get(id)?.production&&byUpdate.get(id)?.version)) return '';
    const images=edition.images || [];
    const valid=Array.isArray(images)&&images.every(image=>assetHref(image.file)&&Number(image.width)>0&&Number(image.height)>0&&/^[a-f0-9]{64}$/.test(image.sha256 || ''));
    const pictures=!valid?'精选图片记录不完整，请查看精选页状态。':images.length?`精选页列出${images.length}张PNG。`:'精选图片尚无记录，请查看精选页状态。';
    return `本期可读${ids.length}条；${pictures}`;
  }
  const notice = () => readingPolicy ? conciseNotice() : production ? `<div class="prototype-notice production-notice"><strong>${production.status==='public'?'本期更新':'本地预览 · 未公开'}</strong><span>编制 ${timeText(production.compiledAt)}${production.researchCutoff||production.sourceDiscoveryCutoff?'<br>':' · '}${cutoffHTML(production)}<br>${esc(coverageText(production.coverageNote || '已核查内容按其资料日期呈现。'))}${currentEditionText()?`<br>${esc(currentEditionText())}`:''}</span></div>` : real ? `<div class="prototype-notice"><strong>真实资料样稿 · 待验收</strong><span>研究截止 ${fmt(D.meta.researchCutoff)} · 有限样本，非当日全量日报。${publicOutput?'':'<a href="#review">范围与暂缓记录 ↗</a>'}</span>${publicOutput?'':'<a class="mode-link" href="?mode=demo#home">原型示例</a>'}</div>` : '<div class="prototype-notice"><strong>原型示例</strong><span>事件、日期、金额及分析均为模拟；对象身份沿用素材，未更新。</span><a class="mode-link" href="?mode=real#home">真实样稿</a></div>';
  const editionDate = () => `<div class="edition-date"><strong>${fmt(readingPolicy?(D.meta.discoveryCoverage?.windowEnd||production?.windowEnd):production?String(production.compiledAt).slice(0,10):real?D.meta.researchCutoff:D.meta.editionDate)}</strong><span>${readingPolicy?'目录查询至（有覆盖边界）':production?'本期编制':real?'研究截止':'示例刊期'}</span></div>`;
  function sourceHTML(s, index) {
    if (typeof s === 'string') return `<p>${esc(s)}</p>`;
    const url = /^https?:\/\//.test(s.url || '') ? s.url : '';
    return `<div class="source-record"><p><span class="source-id">[来源${index+1}${!publicOutput&&s.id?' · '+esc(s.id):''}]</span> ${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a>`:esc(s.title)}</p><p class="small muted">${esc(s.publisher)} · 资料日期 ${esc(s.date||'未提供')}<br>定位：${esc(s.location)}<br>检索：${esc(s.retrievedAt)}${s.note?`<br>${esc(s.note)}`:''}${!publicOutput&&s.localPath?`<br><a href="${esc(s.localPath)}" target="_blank" rel="noopener">本地留存依据 ↗</a>`:''}</p></div>`;
  }
  function tableHTML(table, type) {
    return `<div class="table-scroll" role="region" aria-label="${esc(type)}明细表，可横向滚动" tabindex="0"><table>${table.caption?`<caption>${esc(table.caption)}</caption>`:''}<thead><tr>${table.columns.map(c=>`<th scope="col">${esc(c)}</th>`).join('')}</tr></thead><tbody>${table.rows.map(row=>`<tr>${row.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function filters(items) { const s = pageState(); return `<div class="filters" aria-label="当前页内容筛选">${items.map(t=>`<button class="filter ${s.filter===t?'active':''}" data-action="filter" data-value="${esc(t)}" aria-pressed="${s.filter===t}">${esc(t)}</button>`).join('')}</div>`; }
  function sectionTabs(items) { return `<div class="section-tabs" aria-label="页面内容切换">${items.map(([id,text,count])=>`<button data-action="tab" data-value="${id}" class="${pageState().tab===id?'active':''}" aria-pressed="${pageState().tab===id}">${text}${count?`<em>${count}</em>`:''}</button>`).join('')}</div>`; }
  function currentWorkflow(u) { const r=D.meta.workflowCorrections?.[u.id]; return r?.contentVersion===u.version ? r : null; }
  function summaryFor(u) { const original = state.versions.has(currentKey+'|'+u.id); return u.revision && original ? u.revision.previousSummary : u.summary; }
  function updateTimes(u) {
    if(!real) return `原发布 ${fmt(u.date)} ${esc(u.time)}`;
    const prepared=u.compiledAt || production?.compiledAt || u.updatedAt;
    const verified=D.meta.verificationTimes?.[u.id];
    return `${esc(real&&u.production&&u.event?.type==='私募基金产品备案'?'基金备案（首次公示日未提供）':u.disclosureLabel||'资料披露')} ${fmt(u.date)}${u.time?' '+esc(u.time):'（时刻未核实）'}<br>事项发生 / 统计时点：${esc(u.occurredAt||'详见本次动态，不以检索日替代')}<br>${u.production?`内容编制 ${timeText(prepared)}${u.publishedAt?'<br>正式发布 '+timeText(u.publishedAt):publicOutput&&production.status==='public'?'':'<br>尚未正式发布'}`:`${production?'历史样稿':'样稿'}编写 ${esc(u.publishedAt||u.updatedAt)}`}<br>${u.production?'资料覆盖截止':'研究截止'} ${esc(u.researchCutoff||(u.production?production?.cutoff:null)||D.meta.researchCutoff)}${verified?`<br>最后核查 ${timeText(verified)}`:''}`;
  }
  function detailHTML(u) {
    const e = u.event;
    const chain = e.updates.slice().sort((a,b) => a.date.localeCompare(b.date));
    const original = state.versions.has(currentKey+'|'+u.id);
    const history = original && u.revision?.previousHistory ? u.revision.previousHistory : u.history;
    return `<div class="event-details" id="details-${u.id}">
      <section class="detail-section"><h4>历史对照${original&&u.revision?.previousHistory?' · 修订前快照':''}</h4><ol class="timeline">${history.map(h=>`<li><time>${fmt(h.date)}</time><span>${esc(h.text)}</span></li>`).join('')}</ol>
      ${chain.length>1?`<div class="history-links" aria-label="${real?'同一事件的资料节点':'同一事件的历次发布'}">${chain.map(h=>`<a href="#history/${h.date}?update=${h.id}">${h.date.slice(5).replace('-','.')} · ${esc(h.stage)}${h.id===u.id?'（本次）':''} ↗</a>`).join('')}</div>`:''}</section>
      <section class="detail-section"><h4>业务理解</h4><ul>${u.business.map(b=>`<li>${esc(b)}</li>`).join('')}</ul></section>
      <section class="detail-section"><h4>关键明细</h4><dl class="detail-grid">${u.details.map(d=>`<div><dt>${esc(d.label)}</dt><dd>${rich(d.value)}</dd></div>`).join('')}</dl>${[...(u.table?[u.table]:[]),...(u.tables||[])].map(t=>tableHTML(t,e.type)).join('')}</section>
      <section class="detail-section"><h4>来源与依据</h4>${u.sources.map(sourceHTML).join('')}<p class="coverage-note">${esc(currentWorkflow(u)?.coverage || u.coverage)}</p></section>
      ${currentWorkflow(u)?`<div class="version-box"><strong>流程说明已修正</strong> · ${esc(currentWorkflow(u).at)}<br>${esc(currentWorkflow(u).note)}<br>原资料日期 ${fmt(u.date)}；原编制时间 ${esc(u.compiledAt)} 保留。历史固定版本见日期回看。</div>`:''}
      ${u.revision?`<div class="version-box"><strong>内容已修订</strong> · ${esc(u.revision.at)}<br>${esc(u.revision.note)}<br>${real?`${u.production?'原内容编制':'样稿原编写'} ${esc(u.production?(u.compiledAt||u.updatedAt):u.publishedAt)}；资料日期 ${fmt(u.date)}${u.production&&u.publishedAt?'；原正式发布 '+timeText(u.publishedAt):''}`:`原发布日期 ${fmt(u.date)} ${u.time}`} 保留。<br><button data-action="version" data-id="${u.id}">${original?'查看当前修订版':'查看原发布版本'}</button>${original?`<p>${u.revision.previousHistory?'上方正在展示修订前历史快照，日期归组已更正':'上方“本次动态”正在展示原发布快照，其中错误表述已更正'}，请以修订版为准。</p>`:''}</div>`:''}
      <div class="event-footer"><span>${updateTimes(u)}<br>修订 / 更新 ${esc(u.updatedAt)}</span><button class="collapse-bottom" data-action="collapse" data-id="${u.id}">${u.depth==='brief'?'收起来源与补充说明':'收起历史与业务分析'} ↑</button></div>
    </div>`;
  }
  function eventHTML(u) {
    if(u.reading?.level==='brief') return briefHTML(u,true);
    const open = state.opened.has(u.id);
    const expandable = u.depth !== 'brief' || Boolean(u.production && u.sources?.length);
    const detailName = u.depth === 'brief' ? '来源与补充说明' : '历史与业务分析';
    return `<article class="event" id="entry-${u.id}" data-event-id="${u.event.id}" data-update-id="${u.id}"><div class="event-meta"><span class="event-type">${esc(u.event.type)}</span><span class="meta-sep">/</span><span>${types[u.object.type]}</span><span class="meta-sep">·</span><time datetime="${u.date}${u.time?'T'+u.time:''}">${real?`${esc(real&&u.production&&u.event?.type==='私募基金产品备案'?'基金备案（首次公示日未提供）':u.disclosureLabel||'资料披露')} ${fmt(u.date)}`:`${route().page==='object'?fmt(u.date)+' · ':''}${u.time}`}</time><span class="sample-label">${updateLabel(u)}</span>${u.revision?'<span class="revision-label">已修订</span>':''}${u.event.updates.length>1?'<span>连续跟踪</span>':''}</div><h3><a class="object-link" href="#object/${u.object.id}" title="查看对象与历史">${esc(objectName(u))}</a><span class="title-sep">｜</span>${esc(displayTitle(u))}</h3><p class="event-summary"><span class="summary-prefix">${u.revision&&summaryFor(u)!==u.summary?'修订前正文 · 已更正':'本次动态'}</span>${rich(summaryFor(u))}</p>${!expandable?'':`<button class="expand-toggle" data-action="expand" data-id="${u.id}" aria-expanded="${open}" aria-controls="details-${u.id}">${open?'收起':'展开'}${detailName} ${chevron}</button>${open?detailHTML(u):''}`}</article>`;
  }
  function feedHTML(list, singleDate = false) {
    list=list.filter(readable);
    if (!list.length) return real ? `<div class="empty-state"><strong>${production?'当前范围没有可阅读的合格内容':'本轮没有已完成核查的样稿'}</strong>这不代表没有发生真实事件。${publicOutput?'': '<br><a class="text-link" href="#review">查看研究范围与暂缓原因 ↗</a>'}</div>` : '<div class="empty-state"><strong>这个筛选下还没有示例动态</strong>当前原型只编排少量内容；没有示例不代表没有真实事件。<br><button data-action="filter" data-value="全部">查看全部动态</button></div>';
    const groupDates = [...new Set(list.map(u=>u.date))].sort().reverse();
    return `<div class="feed">${groupDates.map(date=>{
      const dayItems = list.filter(u=>u.date===date).sort((a,b)=>String(b.time||'').localeCompare(String(a.time||'')));
      const priority = dayItems.filter(u=>u.important), other = dayItems.filter(u=>!u.important);
      return `<section class="date-group" aria-label="${fmt(date)}动态"><div class="date-gutter"><div class="day">${date.slice(5).replace('-','.')}</div><div class="year">${date.slice(0,4)}</div><div class="day-label">${real?'资料日期':date===dates[0]?'最新刊期':'历史刊期'}</div></div><div class="date-body">${priority.length?`<h2 class="group-heading"><span class="priority-dot"></span>${production?'当日重点':real?'当日样本重点':date===dates[0]?'今日重点':'当日重点'}<span class="count">${priority.length} 条</span></h2>${companyRows(priority)}`:''}${other.length?`<h2 class="group-heading ${priority.length?'other-heading':''}">其他动态 <span class="count">${other.length} 条</span></h2>${companyRows(other,true)}`:''}</div></section>`;
    }).join('')}</div>${!singleDate?`<div class="end-note">已读完当前范围内的${production?'已核查动态':real?'真实样稿':'原型动态'}。<a href="#history">按日期回看 ↗</a></div>`:''}`;
  }
  function briefHTML(u, withName=false) {
    const source=(u.sources||[]).filter(s=>/^https?:\/\//.test(s.url||''));
    return `<article class="brief-row" id="entry-${u.id}" data-event-id="${u.event.id}" data-update-id="${u.id}">${withName?`<a class="object-link" href="#object/${u.object.id}">${esc(objectName(u))}</a>｜`:''}<span class="brief-kind">${esc(u.event.type)}</span>：${rich(u.summary)} ${source[0]?`<a class="brief-original" href="${esc(source[0].url)}" target="_blank" rel="noopener">原文 ↗</a>`:''}${source.length>1?`<details class="brief-sources"><summary>其余依据（${source.length-1}）</summary>${source.slice(1).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)} · ${esc(s.date)} ↗</a>`).join('')}</details>`:''}</article>`;
  }
  function companyRows(list, compact=false) {
    const ids=[...new Set(list.map(u=>u.object.id))];
    return ids.map(id=>{
      const rows=list.filter(u=>u.object.id===id);
      if(!compact||rows.some(u=>u.reading?.level!=='brief'))return rows.map(eventHTML).join('');
      const heading=`<h3><a class="object-link" href="#object/${id}">${esc(objectName(rows[0]))}</a><span class="code">${esc(rows[0].object.code)}</span></h3>`;
      if(rows.length===1)return `<section class="brief-company">${heading}${briefHTML(rows[0])}</section>`;
      const order={'经营情况':0,'诉讼仲裁及案件进展':1,'融资担保进展':2};
      const selected=rows.slice().sort((a,b)=>(order[a.event.type]??3)-(order[b.event.type]??3)).slice(0,2);
      const requested=route().query.get('update');
      return `<section class="brief-company">${heading}<p class="brief-digest">${selected.map(u=>rich(displayTitle(u))).join('；')}。</p><details class="brief-company-details"${rows.some(u=>u.id===requested)?' open':''}><summary>查看当日 ${rows.length} 项及原文</summary>${rows.map(u=>briefHTML(u)).join('')}</details></section>`;
    }).join('');
  }
  function conciseNotice() {
    const p=production||{},coverage=D.meta.discoveryCoverage;
    const s=D.meta.shareStatus,current=s?.sourceEditionId===p.id;
    const shareText=current&&s.status==='no_eligible_highlights'?'本期暂无可入图新重点':current&&['pending_retry','share_failed'].includes(s.status)?'本期图片待完成':current&&['committed','reused'].includes(s.status)&&s.selectionMode==='current'?'本期精选已导出':'历史精选可回看';
    return `<div class="reading-notice"><span>${coverage?'最近全方向查询范围':'本期资料范围'} ${fmt(coverage?.windowStart||p.windowStart)}—${fmt(coverage?.windowEnd||p.windowEnd)}${coverage?.partial?' · 来源覆盖有缺口':''} · 已核内容陆续更新</span>${publicOutput?'':'<a href="#review">核查与覆盖记录 ↗</a>'}<span class="small muted">${p.status==='public'?'':'本地预览 · 未公开 · '}${shareText}</span></div>`;
  }
  function hasTopic(event,topic) { const tags=event.topics||[]; return tags.includes(topic)||(topic==='并购'&&tags.includes('并购重组'))||(topic==='股权融资'&&['股权融资','企业股权融资','陕西企业股权融资'].includes(event.type)); }
  function applyFilter(list) { const f = pageState().filter; if (f==='全部'||f==='全部动态') return list; return list.filter(u=>u.reading?.group===f||u.event.type===f||types[u.object.type]===f||hasTopic(u.event,f)); }
  function directoryHTML(type) {
    const count = D.objects.filter(o=>o.type===type).length;
    return `<div class="directory-toolbar"><label class="search-field"><input id="directory-search" type="search" placeholder="输入名称、代码或登记编号" aria-label="筛选观察对象" value="${esc(pageState().query || '')}"></label><span class="small muted">${count} 个${publicOutput?'公开对象':'素材对象 · 名单未更新'}</span></div><div class="directory" id="directory-results">${directoryRows(type,pageState().query || '')}</div><p class="section-note">${publicOutput?'对象身份以已公开核实的字段及其资料时点为准；未收录动态不代表没有发生事件。':'基础身份沿用用户素材；未编排动态的对象仅展示已有身份，本轮未核查其近期事件。'}</p>`;
  }
  function objectRow(o) { return `<a class="directory-row" href="#object/${o.id}"><h3>${esc(o.name)}</h3><span class="code">${esc(o.code)}</span><span class="relation">${esc(relationText(o))}</span><span class="arrow" aria-hidden="true">↗</span></a>`; }
  function directoryRows(type, query) { const q=query.trim().toLowerCase(); const items = D.objects.filter(o=>(!type||o.type===type)&&`${o.name} ${o.code}`.toLowerCase().includes(q)); return items.length?items.map(objectRow).join(''):'<p class="empty-state">未找到匹配对象，请尝试简称、代码或登记编号。</p>'; }
  function renderFeedPage(page) {
    const config=views[page], s=pageState();
    if(page==='private'&&D.meta.privateFilingHistory&&!s.filingDefaultApplied){s.tab='filings';s.filingDefaultApplied=true;}
    let list=updates, fs=['全部','上市公司','证券私募','大型平台','并购','股权融资'];
    if (['listed','private','platform'].includes(page)) list=list.filter(u=>u.object.type===page);
    if (page==='listed') fs=readingPolicy?['全部',...readingPolicy.groups,'其他动态']:real?['全部',...new Set(list.map(u=>u.event.type))]:['全部','现金管理','减持','并购','回购','股份解押'];
    if (page==='private') fs=['全部','产品备案','人员变化','机构变化','新纳入'];
    if (page==='platform') fs=real?['全部',...new Set(list.map(u=>u.event.type))]:['全部','基金设立'];
    if (page==='mergers') { list=list.filter(u=>hasTopic(u.event,'并购')); fs=[]; }
    if (page==='equity') { list=list.filter(u=>hasTopic(u.event,'股权融资')); fs=[]; }
    let html=heading(config,page==='home'?editionDate():'')+notice();
    if(page==='home'&&production)html+='<div class="selection-entry"><a href="#share">查看业务重点快讯与分享图 ↗</a></div>';
    if (page==='listed'||page==='private') html+=sectionTabs([['recent','最近动态'],...(page==='private'&&D.meta.privateFilingHistory?[['filings','年内备案']]:[]),['directory','观察对象',D.objects.filter(o=>o.type===page).length]]);
    if(page==='private'&&s.tab==='filings')return html+privateFilingsHTML();
    if (s.tab==='directory' && ['listed','private'].includes(page)) return html+directoryHTML(page);
    if (page==='mergers') html+=production?'<p class="section-note">同一交易按事项连续记录；本期来源覆盖边界见上方说明。</p>':real?'<p class="section-note">样本可从全部110家上市观察对象中选取；本轮仅核查下列交易，未扫描整个观察池。</p>':'<p class="section-note">覆盖全部 110 家上市观察对象，并关注陕西企业作为收购方或标的的交易。</p>';
    if (page==='platform') html+=real?'<p class="section-note">本轮只研究选定重大事项，平台对象目录待名单明确后完善。</p>':'<p class="section-note">平台名单待明确；当前展示重大事项示例。</p>';
    if (fs.length) html+=filters(fs);
    const filtered=applyFilter(list);
    if(readingPolicy&&production) {
      const since=D.meta.discoveryCoverage?.windowStart||production.windowStart;
      const recent=filtered.filter(u=>u.date>=since), older=filtered.filter(u=>u.date<since);
      return html+feedHTML(recent,true)+(older.length?'<h2 class="edition-section-title archive-section-title">历史补充与回看 <span>保留原资料日期</span></h2>'+feedHTML(older):'');
    }
    if(production) {
      const currentIds=new Set(production.updateIds || D.editions.find(e=>e.id===production.id)?.updateIds || []);
      const current=filtered.filter(u=>currentIds.has(u.id));
      const historical=filtered.filter(u=>!currentIds.has(u.id));
      if(current.length) return html+`<h2 class="edition-section-title" id="current-edition">本轮新编与更新 <span>资料日期分别保留</span></h2>`+feedHTML(current,true)+(historical.length?'<h2 class="edition-section-title archive-section-title">历史内容 <span>按原资料日期回看</span></h2>'+feedHTML(historical):'<div class="end-note">已读完当前筛选的本轮内容。<a href="#history">历史回看 ↗</a></div>');
    }
    return html+feedHTML(filtered);
  }
  function privateFilingsHTML(managerId=null) {
    const h=D.meta.privateFilingHistory;
    if(!h)return '';
    const managers=h.managers.filter(m=>!managerId||m.objectId===managerId);
    const products=h.products.filter(p=>!managerId||p.objectId===managerId);
    const complete=managers.length>0&&managers.every(m=>m.status==='complete');
    const count=month=>products.filter(p=>p.filedAt.startsWith(month)).length;
    return `<section class="private-filings"><h2 class="object-section-title">${h.start.slice(0,4)}年产品备案</h2><p class="section-note">${fmt(h.start)}—${fmt(h.end)} · ${managerId?'本管理人':h.scopeCount+'家名单管理人'} · 年内已查得 ${products.length} 只。核对 ${timeText(h.checkedAt)}。</p><p class="section-note">${esc(h.notice)}</p><div class="table-scroll"><table><thead><tr><th>备案月份</th><th>已查备案数量</th><th>覆盖情况</th></tr></thead><tbody>${h.months.slice().reverse().map(m=>`<tr><td>${esc(m.month)}${m.month===h.end.slice(0,7)?'（截至'+esc(h.end.slice(5).replace('-','月'))+'日）':''}</td><td>${!complete&&!count(m.month)?'未完整覆盖':(complete?'':'至少 ')+count(m.month)+' 只'}</td><td>${complete?'名单内当前公示分页已核':managers.filter(m=>m.status==='complete').length+'/'+managers.length+'家完整，其余有缺口'}</td></tr>`).join('')}</tbody></table></div>${h.months.slice().reverse().map(m=>{const list=products.filter(p=>p.filedAt.startsWith(m.month));return list.length?`<details class="filing-month"><summary>${esc(m.month)} · ${list.length}只 · 查看产品明细</summary>${list.map(p=>`<div class="filing-product"><strong>${esc(p.name)}</strong><span class="code">${esc(p.filingNo)}</span><p>${esc(p.managerName)} · 备案 ${fmt(p.filedAt)}<br>当前公示托管：${esc(p.custodian||'未披露')} · ${esc(p.state||'状态未提供')} · 公示核对 ${fmt(p.retrievedAt?.slice(0,10))} <a href="${esc(p.url)}" target="_blank" rel="noopener">AMAC原文 ↗</a></p></div>`).join('')}</details>`:'';}).join('')}${!complete?`<details class="filing-month"><summary>查看未完整覆盖的管理人</summary>${managers.filter(m=>m.status!=='complete').map(m=>`<p>${esc(m.name)} · ${esc(m.registrationNo)} · ${m.status==='partial'?'部分取得':'未完整取得'}</p>`).join('')}</details>`:''}</section>`;
  }
  function identityHTML(o) {
    const marketName={SZ:'深圳证券交易所',SH:'上海证券交易所',BJ:'北京证券交易所',HK:'香港交易所'};
    const items=o.type==='listed'?[['证券代码',o.code],['市场',marketName[o.market]||o.market],['基础身份','上市观察对象']]:o.type==='private'?[['登记编号',o.code],['注册地',o.registerProvince||'素材未提供'],['办公地',o.officeProvince||'素材未提供'],['办公地址',o.officeAddress||'素材未提供']]:[['基础身份',o.code],['对象说明',o.summary]];
    return `<section class="identity" aria-label="对象基础身份"><p class="relation-line"><span class="identity-label">陕西关联原因</span>${esc(relationText(o))}</p><dl class="identity-grid">${items.map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl><p class="small muted">${publicOutput?`基础身份资料时点 ${o.asOf?fmt(o.asOf):'见本次动态来源'}；仅显示已获准公开字段。`:o.type==='listed'||o.type==='private'?`基础身份来自用户素材 · 资料日期 ${fmt(o.asOf)} · 名单未更新${real?'；本轮事项身份核对见来源':''}`:`${esc(o.source)}${real?' · 仅核查本轮事项所需身份':' · 仅演示页面，未补充真实工商或经营资料'}`}</p>${real&&o.identityNote?`<p class="coverage-note">${esc(o.identityNote)}</p>`:''}</section>`;
  }
  function objectHistoryHTML(o,list,kind) {
    let events=D.events.filter(e=>e.objectId===o.id).map(e=>({...e,updates:e.updates.filter(u=>list.some(v=>v.id===u.id))})).filter(e=>e.updates.length);
    if (kind==='products') events=events.filter(e=>e.type==='产品备案');
    if (kind==='changes') events=events.filter(e=>['人员变化','机构变化'].includes(e.type));
    if (!events.length) return `<div class="empty-state"><strong>${real?'本轮未核查这部分历史':'这部分历史尚未编排示例'}</strong>当前素材仅提供基础身份，不能据此认定该对象没有相关历史。</div>`;
    if (kind==='products') return `<h2 class="object-section-title">产品备案与托管记录</h2><p class="section-note">以下为同一份产品动态中的记录。不同产品使用不同托管机构，不等于存续产品发生托管变更。</p>${events.map(e=>{const u=byUpdate.get(e.updates[0].id);return `${u.table?`<div class="table-scroll"><table><thead><tr>${u.table.columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${u.table.rows.map(row=>`<tr>${row.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:''}<a class="text-link" href="#object/${o.id}?update=${u.id}">阅读本次产品备案与业务分析 ↗</a>`;}).join('')}`;
    return `<h2 class="object-section-title">${kind==='changes'?'人员与主体变化':'资本事件历史'}</h2><p class="section-note">每个事件保留独立脉络，后续进展接续记录。${real?'仅呈现本轮核实的披露节点。':'以下均为原型示例。'}</p>${events.map(e=>{const chain=e.updates.slice().sort((a,b)=>a.date.localeCompare(b.date));return `<section class="object-event-line"><time>${esc(e.type)}<br>${chain.length} ${real?'个资料节点':'次发布'}</time><div><h3>${esc(chain[chain.length-1].title)}</h3><ol class="timeline" style="margin-top:15px">${chain.map(u=>`<li><time>${fmt(u.date)}</time><a href="#object/${o.id}?update=${u.id}">${real?esc(u.disclosureLabel||'资料披露')+' · ':''}${esc(u.stage)}${u.revision?' · 已修订':''} ↗</a></li>`).join('')}</ol></div></section>`;}).join('')}`;
  }
  function renderObject(id) {
    const o=objects.get(id); if(!o) return notFound();
    const parent=['listed','private','platform'].includes(o.type)?o.type:'equity';
    let list=updates.filter(u=>u.object.id===id&&readable(u));
    const title=`${esc(o.name)}<span class="object-code">${esc(o.code)}</span>`;
    let html=`<div class="breadcrumb"><a href="#${parent}">${types[o.type]}</a><span> / 对象档案</span></div>`+heading({object:true,title})+identityHTML(o);
    const tabs=o.type==='private'?[['recent','最近动态'],['products','产品与托管'],['changes','人员与主体']]:[['recent','最近动态'],['capital','资本事件历史']];
    html+=sectionTabs(tabs);
    if(real) html+=notice();
    if(readingPolicy&&o.type==='listed'&&pageState().tab==='recent')return html+feedHTML(list,true);
    if(pageState().tab==='recent') html+=list.length?`<div class="object-content">${list.map(eventHTML).join('')}</div>`:`<div class="empty-state"><strong>${real?'本轮未核查该对象的近期动态':'已保留基础身份，暂未编排动态示例'}</strong>这不代表该对象近期没有动态。<br><a class="text-link" href="#${parent}">返回客群页</a></div>`;
    else html+=`<div class="object-content">${o.type==='private'&&pageState().tab==='products'&&D.meta.privateFilingHistory?privateFilingsHTML(o.id):objectHistoryHTML(o,list,pageState().tab)}</div>`;
    return html;
  }
  function renderHistory(value) {
    const date=dates.includes(value)?value:dates[0];
    let html=heading(views.history)+notice()+sectionTabs([['recent','按日期回看'],['objects','按对象回看']]);
    if(pageState().tab==='objects') return html+`<div class="history-object-picks"><label class="search-field"><input id="history-object-search" type="search" placeholder="搜索公司、管理人或代码" aria-label="搜索历史对象"></label><p class="section-note">先展示当前模式已有动态的对象。其他对象可通过名称或代码查找。</p><div id="history-object-results">${[...new Set(updates.map(u=>u.object.id))].map(id=>objectRow(objects.get(id))).join('')}</div></div>`;
    if(D.publications?.length) html+=`<section class="publication-history"><h2>按发布期回看</h2><p class="section-note">每期保留当时内容快照；下方仍可按资料日期回看。</p><div>${D.publications.map(p=>assetHref(p.snapshotUrl)?`<a href="${esc(assetHref(p.snapshotUrl))}"><strong>${fmt(p.date)}</strong><span>编制 ${timeText(p.compiledAt)}${p.researchCutoff||p.sourceDiscoveryCutoff?'<br>'+cutoffHTML(p):' · 截止 '+timeText(p.cutoff)}</span><span aria-hidden="true">↗</span></a>`:'').join('')}</div></section>`;
    const dateEdition=D.editions.find(e=>e.date===date);
    html+=`<div class="history-toolbar"><label class="date-select">${real?'资料日期':'发布日期'}<select id="history-date" aria-label="选择历史日期">${dates.map(d=>`<option value="${d}" ${d===date?'selected':''}>${fmt(d)}</option>`).join('')}</select></label>${dateEdition?`<a href="#share/${encodeURIComponent(editionKey(dateEdition))}">查看当日精选图 ↗</a>`:'<span class="small muted">当日未编排精选图</span>'}</div><p class="archive-intro">${production?'按来源披露/公示更新日归档；资料日期、内容编制与正式发布时间分别保留。历史发布快照不倒填后续事实。':real?'按来源披露/公示更新日归档，非产品当日正式发布。样稿编写、事项发生和研究截止时间分别保留；历史节点不倒填后续事实。':'按原发布日期归档；修订条目默认阅读更正版，可展开查看修订说明和修订前正文。后续进展连接至原事件，不改写早期发布的阶段。'}</p>`;
    return html+feedHTML(updates.filter(u=>u.date===date),true);
  }
  // These selections point to the same event fields used by the expanded webpage.
  const shareSelections = {
    'u-ma-0910': {facts:['交易结构','交易金额'], insight:0},
    'u-cash-0910': {facts:['资金性质','授权上限','使用期间','实际投入余额'], insight:0},
    'u-product-0910': {facts:['产品备案日期','本次托管机构','产品规模 / 账户状态'], insight:1},
    'u-platform-0909': {facts:['目标规模','首期拟认缴','平台拟认缴'], insight:0},
    'u-financing-0909': {facts:['本轮轮次','本轮融资额','本轮投资人'], insight:0}
  };
  function shareText(value, u) {
    // Only tidy excerpts. The event text and complete source records stay intact.
    const sourceIds = new Set(u.sources.map(s=>s.id).filter(Boolean));
    return String(value).replace(/\s*\[([^\]\n]+)\]/g, (marker, reference) =>
      sourceIds.has(reference.split(/[，,、\s—–-]/)[0]) ? '' : marker
    ).trim().replace(/[。；;，,]+$/, '');
  }
  function shareExcerpt(u) {
    if(u.shareContent) {
      const facts=Array.isArray(u.shareContent.facts)?u.shareContent.facts:[u.shareContent.facts];
      return facts.map(text=>`<p class="share-facts">${rich(text)}</p>`).join('')+`<p class="share-insight">${esc(u.shareContent.insight)}</p>`;
    }
    if(u.production) return '';
    const selection=real?u.share:shareSelections[u.id];
    if(!selection) return ''; 
    const facts=selection.facts.map(label=>u.details.find(d=>d.label===label)).filter(Boolean);
    const insight=shareText(u.business[selection.insight].split('。')[0],u).replace(/^业务理解\s*[：:｜|]\s*/, '')+'。';
    return `<p class="share-facts">${facts.map(d=>`<span data-source-label="${esc(d.label)}">${esc(d.label)}：${rich(shareText(d.value,u))}</span>`).join('；')}。</p><p class="share-insight" data-source-business="${selection.insight}"><span class="insight-label">业务理解</span>${esc(insight)}</p>`;
  }
  function shareSheetHTML(date,items,index,total) {
    const historical=production&&real;
    const label=historical?'历史真实样稿':sampleLabel;
    const entry=publicOutput?(production?.publicUrl||'完整网页入口待确认'):`仅本机预览：http://localhost:4173/${real?'?mode=real':''}#${real?'home':'history/'+date}`;
    const cutoff=[...new Set(items.map(u=>u.researchCutoff).filter(Boolean))].join(' / ')||D.meta.researchCutoff;
    const note=real?`${historical?'历史真实样稿':'真实资料样稿 · 待验收'}；日期为样稿整理日，非同日市场日报。各事件资料日期（披露／公示更新）见标题上方，研究截止 ${esc(cutoff)}。内容摘自同一份网页样稿。${publicOutput?'':'尚无公开访问地址。'}`:'原型示例 · 本图事件、日期、金额及分析均为模拟，不是真实市场信息。内容与网页同源，所用对象基础身份未联网更新。';
    return `<div class="share-sheet" id="share-sheet-${index+1}" data-date="${date}"><div class="share-brand">陕西资本观察 <span style="color:var(--warm)"> / </span><span class="share-prototype">${label}</span></div><h2>${real?'真实样稿精选':'每日综合精选'}</h2><div class="share-dateline">${fmt(date)}<span>${String(index+1).padStart(2,'0')} / ${String(total).padStart(2,'0')}</span></div>${items.map((u,i)=>`<section class="share-event" data-update-id="${u.id}"><p class="share-category">${String(index*2+i+1).padStart(2,'0')} &nbsp; ${types[u.object.type]} · ${esc(u.event.type)}${real?' · 资料 '+fmt(u.date):''}</p><h3>${esc(objectName(u))}｜${esc(displayTitle(u,u.shareContent?.title||u.title))}</h3>${shareExcerpt(u)}</section>`).join('')}<div class="share-footer">完整内容、历史对照与业务理解，请进入网页阅读 ↗<div class="share-entry">${esc(entry)}</div></div><p class="share-sample">${note}</p></div>`;
  }
  function renderShare(value) {
    const edition=D.editions.find(e=>e.id===value)||D.editions.find(e=>e.date===value)||D.editions.find(e=>e.presentation==='business-news-20261015')||D.editions.find(e=>e.id===production?.id)||D.editions[0];
    if(!edition) return heading(views.share)+notice()+'<p class="empty-state">本轮暂未选出可用于分享的合格样稿。</p>';
    if(edition.updateIds.some(id=>D.meta.contentHolds?.[id]||D.meta.supersededUpdates?.[id])) return heading(views.share)+notice()+`<p class="coverage-note">本刊含待核或已被替代的进展，暂停作为当前分享。原版及图片仍保留在历史固定刊，仅表达原时点。${edition.snapshotUrl?`<a href="${esc(edition.snapshotUrl)}?mode=real#share/${esc(editionKey(edition))}" target="_blank" rel="noopener">打开历史固定刊与旧PNG ↗</a>`:''}</p><a href="#share">返回当前精选 ↗</a>`;
    const selected=edition.updateIds.map(id=>byUpdate.get(id)).filter(Boolean);
    const editionOptions=D.editions.map(e=>{
      const sameDate=D.editions.filter(other=>other.date===e.date);
      const label=e.presentation?`${fmt(e.date)} · ${e.selectionMode==='historical_preview'?'已核历史选编':'本轮精选'} · ${e.updateIds.length}条${sameDate.length>1?' · 第'+(sameDate.length-sameDate.indexOf(e))+'版':''}`:sameDate.length>1?`${e.date.slice(5).replace('-','.')} · ${e.updateIds.length}条（${e.id===production?.id?'内容刊期':'历史样式·第'+(sameDate.length-sameDate.indexOf(e))+'版'}）`:`${fmt(e.date)} · 历史样式`;
      return `<option value="${esc(editionKey(e))}" ${editionKey(e)===editionKey(edition)?'selected':''}>${esc(label)}</option>`;
    }).join('');
    if(edition.presentation==='business-news-20261015')return renderNewsShare(edition,editionOptions);
    if(edition.id || edition.status || edition.images) {
      const images=(edition.images||[]).filter(i=>assetHref(i.file));
      return heading(views.share)+notice()+`<div class="share-toolbar"><label class="date-select">精选刊期<select id="share-date" aria-label="选择精选日期">${editionOptions}</select></label><span class="small muted">${selected.length} 条精选 · ${images.length} 张图片 · ${edition.status==='public'?'已公开':'本地预览，未公开'}</span><span class="spacer"></span><a class="outline-button" href="#home">回到完整网页 ↗</a></div><p class="section-note">本期 ${fmt(edition.date)}${edition.researchCutoff||edition.sourceDiscoveryCutoff?'<br>':' · '}${cutoffHTML(edition)}。图片与下方同一进展版本对应。</p>${images.length?`<div class="share-gallery share-image-gallery">${images.map((image,i)=>`<figure class="share-item"><a href="${esc(assetHref(image.file))}" target="_blank" rel="noopener"><img class="share-export" src="${esc(assetHref(image.file))}" width="${Number(image.width)||1080}" height="${Number(image.height)||1}" alt="${fmt(edition.date)} 每日综合精选，第${i+1}张，共${images.length}张" loading="${i?'lazy':'eager'}"></a><figcaption class="share-caption"><span>${i+1} / ${images.length} · ${edition.status==='public'?'本期精选':'未公开预览'}</span><a href="${esc(assetHref(image.file))}" download>下载 PNG ↓</a></figcaption></figure>`).join('')}</div>`:`<p class="empty-state">${edition.imagesStatus==='design_pending'?'本轮图片样式待确认，未生成新图。可切换刊期查看历史PNG；新内容请到首页阅读。':selected.length?'本期精选图片待生成。完整内容仍可从下方阅读；未使用历史图片代替。':'本期没有入选精选的内容，不生成空图片。'}</p>`}<section class="share-web-items"><h2>本期精选的完整内容</h2>${selected.map(u=>`<a href="#history/${u.date}?update=${u.id}">${esc(objectName(u))}｜${esc(displayTitle(u))} <span class="muted">↗</span></a>`).join('')}</section>`;
    }
    const sheets=[];for(let i=0;i<selected.length;i+=2)sheets.push(selected.slice(i,i+2));
    return heading(views.share)+notice()+`<div class="share-toolbar"><label class="date-select">精选日期<select id="share-date" aria-label="选择精选日期">${editionOptions}</select></label><span class="small muted">${selected.length} 条精选 · ${sheets.length} 张样稿 · 以手机阅读为先</span><span class="spacer"></span><a class="outline-button" href="#${real?'home':'history/'+edition.date}">${real?'回到样稿网页':'回到当日网页'} ↗</a></div><div class="share-gallery">${sheets.map((items,i)=>`<div class="share-item">${shareSheetHTML(edition.date,items,i,sheets.length)}<div class="share-caption"><span>样稿 ${i+1} / ${sheets.length} · ${production?'历史真实样稿':sampleLabel}</span>${real?`<span>${production?'历史':'网页'}视觉样稿 · 未制作PNG</span>`:`<a href="assets/selection-${edition.date}-${i+1}-r2.png" download>下载 PNG 样稿 ↓</a>`}</div></div>`).join('')}</div><p class="section-note">精选从同一条网页事件的关键明细和业务理解中摘取；完整内容见下方入口。${production?'此处保留历史样稿原日期和视觉记录。':'当前为静态原型样稿，本地入口尚无公开地址。'}</p><section class="share-web-items"><h2>本期精选的完整内容</h2>${selected.map(u=>`<a href="#history/${u.date}?update=${u.id}">${esc(objectName(u))}｜${esc(displayTitle(u))} <span class="muted">↗</span></a>`).join('')}</section>`;
  }
  function renderNewsShare(edition,options) {
    const images=(edition.images||[]).filter(i=>assetHref(i.file)),items=edition.items||[];
    const groups=[...new Set(items.map(i=>i.business))];
    const preview=edition.selectionMode==='historical_preview';
    const status=D.meta.shareStatus;
    const noCurrent=status?.sourceEditionId===production?.id&&status.status==='no_eligible_highlights';
    const failure=status?.sourceEditionId===production?.id&&['pending_retry','share_failed'].includes(status.status);
    return heading({title:'业务重点快讯'})+`<div class="share-toolbar"><label class="date-select">精选版本<select id="share-date" aria-label="选择精选日期">${options}</select></label><span class="spacer"></span><a href="#home">回到完整网页 ↗</a></div>
      <div class="news-edition-note"><strong>${preview?(D.meta.shareDesign?.accepted?'已核历史选编':'已核事件选编 · 版式预览'):'本轮已核精选'}</strong><p>资料 ${fmt(edition.rangeStart)}—${fmt(edition.rangeEnd)} · ${items.length}条 · ${images.length}张</p><p>${images.length?'已导出PNG':'图片待生成'}${D.meta.shareDesign?.accepted?'':' · 新版式待用户验收'} · ${edition.status==='public'?'已公开':'尚未公开'}</p><p>${preview?'仅表达各条原披露时点，不代表今日新发生。':'各条保留真实披露日期。'}编排 ${fmt(edition.date)}。</p></div>
      ${noCurrent?'<p class="section-note">当前内容刊期没有可入图的新重点；下方历史选编不作为本期新图。</p>':''}${failure?'<p class="coverage-note">本期导图尚未完成，保留上一可读版本；失败状态不代表已导出。</p>':''}
      ${images.length?`<p class="small muted">点击图片查看原尺寸；手机可打开后长按保存，或下载PNG。</p><div class="share-gallery share-image-gallery news-gallery${images.length===1?' single-sheet':''}">${images.map((im,i)=>`<figure class="share-item"><a class="image-enlarge" href="${esc(assetHref(im.file))}" target="_blank" rel="noopener" aria-label="放大第${i+1}张精选图"><img class="share-export" src="${esc(assetHref(im.file))}" width="${im.width}" height="${im.height}" alt="${esc(edition.previewLabel)} 第${i+1}张，共${images.length}张" loading="${i?'lazy':'eager'}"></a><figcaption class="share-caption"><span>第${i+1} / ${images.length}张</span><a href="${esc(assetHref(im.file))}" download="陕西资本观察-${edition.date}-${i+1}.png">下载PNG ↓</a></figcaption></figure>`).join('')}</div>`:'<p class="empty-state">本版图片尚未生成，不使用旧图片替代。</p>'}
      <section class="news-directory"><h2>精选事件 · 回到正文</h2>${groups.map(group=>`<div><h3>${esc(group)}</h3>${items.filter(i=>i.business===group).map(i=>`<a href="#history/${i.date}?update=${i.updateId}"><span>${esc(i.objectName)}｜${esc(i.share.title)}</span><small>${fmt(i.date)} ↗</small></a>`).join('')}</div>`).join('')}</section>`;
  }
  function baselineHTML(r) {
    const change = r.latestChangeRecord;
    return `<details class="baseline-record"><summary>${esc(r.name)} · ${esc(r.registrationNo)}</summary><p>${esc(r.currentStateStatus)}</p><dl><dt>本次取得 / 公示信息更新时间</dt><dd>${esc(r.retrievedAt)} / ${esc(r.institutionInfoUpdatedAt)}。只证明取得时可见状态，不代表年初状态。</dd><dt>公示出资人认缴比例 / 实际控制人</dt><dd>${esc(r.shareholders)}；实际控制人：${esc(r.actualController)}</dd><dt>最近列示办理记录</dt><dd>提交 ${esc(change.submittedAt)} · ${esc(change.description)} · ${esc(change.status)}。${esc(change.timingNote)}</dd><dt>本轮结论与缺口</dt><dd>${esc(r.eventEligibility)}。${esc(r.missing)}</dd><dt>与已留存资料比较</dt><dd>${esc(r.comparisonResult)}</dd></dl><p><strong>本轮公示依据</strong></p>${sourceHTML(r.source,0)}<p><strong>此前留存依据（不是年初基线）</strong></p>${sourceHTML(r.priorSource,1)}</details>`;
  }
  function deferredHTML(d) {
    return `<section class="deferred-record"><h3>${esc(d.title)}</h3>${d.researchWindow?`<p><strong>事件回溯范围</strong>　${esc(d.researchWindow)}<br>${esc(d.status)}</p>`:''}<dl><dt>已查范围</dt><dd>${esc(d.searched)}</dd>${d.known?`<dt>本轮结果</dt><dd>${esc(d.known)}</dd>`:''}<dt>关键缺口与影响</dt><dd>${esc(d.reason)}</dd><dt>继续所需依据</dt><dd>${esc(d.needed)}</dd></dl>${d.currentVerification?`<p>${esc(d.currentVerification)}</p>`:''}${d.baselineRecords?.length?`<p><strong>四个候选的公示状态与来源</strong> · 点击名称展开</p>${d.baselineRecords.map(baselineHTML).join('')}`:(d.sources||[]).map(sourceHTML).join('')}</section>`;
  }
  function compactCoverageHTML(r,o) {
    const labels={complete:'成功',partial:'部分覆盖',failed:'失败',not_run:'未执行'};
    const byRun=new Map();
    r.coverage.forEach(c=>{if(!byRun.has(c.runId))byRun.set(c.runId,[]);byRun.get(c.runId).push(c);});
    if(!byRun.size)return '所列窗口未取得该方向完整来源证明';
    return [...byRun].map(([id,rows])=>{
      const w=o.windows.find(x=>x.id===id),date=w?`${fmt(w.windowStart).slice(5)}—${fmt(w.windowEnd).slice(5)}`:id;
      const totals=rows.reduce((a,c)=>{Object.entries(c.counts).forEach(([k,n])=>a[k]=(a[k]||0)+n);return a;},{});
      const text=r.direction==='private'?rows.filter(c=>['管理人状态','产品备案'].includes(c.source)).map(c=>`${c.source} ${c.counts.complete||0}/${Object.values(c.counts).reduce((a,b)=>a+b,0)}成功`).join('；'):Object.entries(totals).map(([k,n])=>`${labels[k]||k} ${n}`).join('，');
      return `<details><summary>${date}：${text}</summary>${rows.map(c=>`<p class="small">${esc(c.source==='池外新管理人发现'?'池外属地查询入口':c.source)}：${Object.entries(c.counts).map(([k,n])=>`${labels[k]||esc(k)} ${n}`).join(' / ')}</p>`).join('')}</details>`;
    }).join('');
  }
  function productionOverviewHTML(review) {
    const o=review.overview;if(!o)return '';
    const names={listed:'上市公司',private:'证券私募',platform:'大型平台',mergers:'并购',equity:'股权融资'};
    const link=(r,kind,n)=>`<a href="#review?direction=${r.direction}&bucket=${kind}">${n}</a>`;
    return `<section class="review-content production-overview"><h2>本轮处理一览</h2><p>固定范围 ${o.originalVersions} 份原件版本，其中 ${o.unresolvedOriginals} 份仍待事项关系核对；不计为已研究或独立事项。</p><p class="small muted">${o.windows.map(w=>`${fmt(w.windowStart)}—${fmt(w.windowEnd)} · 截止 ${timeText(w.cutoff)}`).join('<br>')}</p><div class="table-scroll"><table><thead><tr><th>范围</th><th>实际来源覆盖</th><th>独立事项<br>重点 / 普通</th><th>公开 / 本地合格</th><th>未研究 / 处理中</th><th>待核 / 访问缺口</th></tr></thead><tbody>${o.rows.map(r=>`<tr><td>${names[r.direction]}</td><td>${compactCoverageHTML(r,o)}</td><td>${link(r,'all',r.total)}<br>${r.deep} / ${r.brief}</td><td>${link(r,'published',r.published)} / ${r.localReady}</td><td>${link(r,'unfinished',r.unfinished)}</td><td>${link(r,'hold',r.hold)} / ${r.failures.length}${r.failures.length?`<details><summary>来源缺口</summary>${r.failures.map(f=>`<p>${esc(f.name)} · ${esc(f.status)}<br>${esc(f.reason)}</p>`).join('')}</details>`:''}</td></tr>`).join('')}</tbody></table></div><p class="small muted">${esc(o.limit)}</p></section>`;
  }
  function productionReviewHTML() {
    const review=D.meta.productionReview;
    if(!review||publicOutput)return '';
    const labels={local_ready:'已接入网页',content_qualified:'内容合格待提交',pending_research:'待首次研究',pending_evidence:'待补原件',pending_quality:'待独立核查',quality_hold:'核查未通过',evidence_hold:'具体证据暂缓',processing_incomplete:'执行未完成',relation_pending:'新增依据关系待核',evidence_change_pending:'新增依据待定点修订'};
    const dir=route().query.get('direction'),bucket=route().query.get('bucket');
    const allowed=review.overview?.rows.find(r=>r.direction===dir)?.ids[bucket||'all'];
    const rows=review.matters.filter(m=>!allowed||allowed.includes(m.id)).sort((a,b)=>(a.status==='local_ready'?-1:0)-(b.status==='local_ready'?-1:0)||b.date.localeCompare(a.date));
    return productionOverviewHTML(review)+`<section class="review-content production-work-review"><h2>当前生产事项与进展</h2>${dir?'<p><a href="#review">显示全部事项 ↗</a></p>':''}<p>${Object.entries(review.counts).map(([k,v])=>`${esc(labels[k]||k)} ${v}项`).join(' · ')}。另保留${review.mergedHistoryRows}条已归并历史任务，不重复排队或计作待研究。</p><p class="small muted">${esc(review.limit)}</p>${rows.map(m=>`<details class="production-matter" data-matter-id="${esc(m.id)}"><summary>${esc(objects.get(m.objectId)?.name||m.objectId)}｜${esc(m.type)} · ${esc(labels[m.status]||m.status)}<br><span class="small muted">${fmt(m.date)} · ${esc(m.stage)}</span></summary>${m.product?`<p>${Object.entries(m.product.fields).map(([k,v])=>`${esc(k)}：${esc(v)}`).join(' · ')}</p><p class="small muted">${esc(m.product.status)}</p>`:''}${m.reason?`<p>${esc(m.reason)}</p>`:''}<p class="small muted">最后步骤 ${esc(m.lastStep||'尚未研究')} · ${timeText(m.lastAttemptAt)}</p>${m.issues?.length?`<ul>${m.issues.map(i=>`<li>${esc(typeof i==='string'?i:[i.field,i.reason].filter(Boolean).join('：'))}</li>`).join('')}</ul>`:''}${m.needs?.length?`<ul>${m.needs.map(n=>`<li>${esc(n.claim||n.reason||'待核资料')} ${n.url?`<a href="${esc(n.url)}" target="_blank" rel="noopener">原件入口 ↗</a>`:''}</li>`).join('')}</ul>`:''}<p class="small muted">首次入队 ${timeText(m.firstQueuedAt)}${m.retainedBranches?' · 已归并'+m.retainedBranches+'条历史分支，原候选、核查和失败记录保留':''}</p>${m.updateId&&byUpdate.has(m.updateId)?`<p><a href="#history/${byUpdate.get(m.updateId).date}?update=${m.updateId}">阅读对应内容 ↗</a></p>`:''}<ul>${m.sources.map(r=>`<li><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a> <span class="muted">${fmt(r.date)}</span></li>`).join('')}</ul></details>`).join('')}</section>`;
  }
  function renderReview() {
    if(publicOutput) return heading({title:'更新与覆盖说明'})+notice()+`<section class="review-content"><p>${esc(coverageText(production?.coverageNote || '本页仅提供已确认的公开内容与覆盖说明。'))}</p><a class="text-link" href="#home">返回综合动态 ↗</a></section>`;
    if(!real) return heading(views.review)+notice();
    const review=D.review||{};
    return heading(views.review)+(production?notice():window.DISCOVERY?'<div class="prototype-notice"><strong>第3阶段 · 手动发现验收</strong><span>正式阅读仍保留第2阶段样稿及其资料时点。</span><a class="mode-link" href="?mode=demo#home">原型示例</a></div>':notice())+productionReviewHTML()+(window.renderDiscovery?.()||(window.DISCOVERY?.error?`<p class="coverage-note">${esc(window.DISCOVERY.error)}</p>`:''))+`<section class="review-content"><h2>第2阶段样稿与保留项</h2><p>${esc(review.scope||'本轮按有限核心事项选样，未更新观察池，不代表当日市场全貌。')}</p><p>内容编写于 ${fmt(D.meta.researchCutoff)}；首页按来源披露或公示更新日期回看。对象池身份按素材原日期保留，未研究对象标为“本轮未核查”。</p><h2>可阅读样稿</h2><ul>${D.events.filter(e=>e.updates.some(u=>!u.production)).map(e=>{const old=e.updates.filter(u=>!u.production),u=old[old.length-1];return `<li><a href="#object/${e.objectId}?update=${u.id}">${esc(objects.get(e.objectId)?.name)} · ${esc(e.type)}</a><span class="muted">　资料日期 ${fmt(u.date)} · ${old.length} 个已核实披露节点</span></li>`;}).join('')}</ul><h2>暂缓事项</h2><p>以下内容不进入动态流、搜索推荐或精选；已完成的其他样稿可独立阅读。</p>${(review.deferred||[]).map(deferredHTML).join('')||'<p>本轮没有暂缓事项。</p>'}<h2>同源复做核对</h2>${(review.rechecks||[]).map(r=>`<p><strong>${esc(r.title)}</strong>　${esc(r.result)}</p>`).join('')||'<p>复做核对尚未完成，当前仍在整理。</p>'}<p class="coverage-note">${esc(review.limit||'有限样本支持内容验收，不构成稳定日更或自动生产能力的证明。')}</p><p><a href="research/制作说明.md" target="_blank">查看简短制作说明与核查口径 ↗</a></p></section>`;
  }
  function notFound() { return '<div class="empty-state"><strong>未找到这个页面</strong><a class="text-link" href="#home">返回综合首页</a></div>'; }
  function render() {
    const r=route(),s=pageState();
    document.querySelectorAll('[data-nav]').forEach(a=>{ const active=a.dataset.nav===r.page; a.classList.toggle('active',active); if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current'); });
    if(r.page==='object') main.innerHTML=renderObject(r.value);
    else if(r.page==='history') main.innerHTML=renderHistory(r.value);
    else if(r.page==='share') main.innerHTML=renderShare(r.value);
    else if(r.page==='review') main.innerHTML=renderReview();
    else if(views[r.page]) main.innerHTML=renderFeedPage(r.page);
    else main.innerHTML=notFound();
    const title=r.page==='object'?objects.get(r.value)?.name:views[r.page]?.title;
    document.title=`${title || '页面'} · 陕西资本观察 · ${sampleLabel}`;
    persist();
  }
  function repaintEvent(id, action) {
    const article=document.getElementById('entry-'+id),u=byUpdate.get(id);if(!article||!u)return;
    const wasAbove=article.getBoundingClientRect().top<document.querySelector('.site-header').offsetHeight+12;
    article.outerHTML=eventHTML(u);
    const next=document.getElementById('entry-'+id);
    const control=next.querySelector(action==='version'?'[data-action="version"]':'.expand-toggle');
    control?.focus({preventScroll:true});
    if(action==='collapse'&&wasAbove)next.scrollIntoView({block:'start'});
    persist();
  }
  document.addEventListener('click',event=>{
    const anchor=event.target.closest('a[href^="#"]');
    if(anchor?.getAttribute('href')==='#main'){event.preventDefault();main.focus({preventScroll:true});main.scrollIntoView({block:'start'});return;}
    if(anchor&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&anchor.getAttribute('href')!=='#main') {event.preventDefault();document.querySelector('#search-dialog').close();navigate(anchor.getAttribute('href').slice(1));return;}
    const button=event.target.closest('[data-action]');if(!button)return;
    const {action,value,id}=button.dataset;
    if(action==='expand'||action==='collapse') {if(action==='collapse'||state.opened.has(id))state.opened.delete(id);else state.opened.add(id);repaintEvent(id,action);}
    if(action==='version') {state.versions.has(currentKey+'|'+id)?state.versions.delete(currentKey+'|'+id):state.versions.add(currentKey+'|'+id);repaintEvent(id,action);}
    if(action==='filter') {pageState().filter=value;render();main.querySelector(`.filter.active`)?.focus({preventScroll:true});}
    if(action==='tab') {pageState().tab=value;render();main.querySelector('.section-tabs .active')?.focus({preventScroll:true});}
    if(action==='search') {const dialog=document.querySelector('#search-dialog');dialog.showModal();const field=document.querySelector('#global-search');field.value='';renderSearch('');field.focus();}
    if(action==='close-search') document.querySelector('#search-dialog').close();
  });
  function renderSearch(query) { const list=D.objects.filter(o=>`${o.name} ${o.code}`.toLowerCase().includes(query.trim().toLowerCase()));const displayed=query?list.slice(0,40):[...new Set(updates.map(u=>u.object.id))].map(id=>objects.get(id));document.querySelector('#search-results').innerHTML=`<p class="result-note">${query?`找到 ${list.length} 个对象${list.length>40?'，显示前 40 个；请补充关键词缩小范围':''}`:real?'本轮已有真实样稿的对象':'已编排动态示例的对象'}</p>${displayed.map(objectRow).join('')}${!displayed.length?'<p class="empty-state">未找到匹配对象。</p>':''}`; }
  document.addEventListener('input',event=>{
    if(event.target.id==='global-search')renderSearch(event.target.value);
    if(event.target.id==='directory-search') {pageState().query=event.target.value;document.querySelector('#directory-results').innerHTML=directoryRows(route().page,event.target.value);persist();}
    if(event.target.id==='history-object-search') document.querySelector('#history-object-results').innerHTML=directoryRows(null,event.target.value);
  });
  document.addEventListener('change',event=>{
    if(event.target.id==='history-date')navigate('history/'+event.target.value);
    if(event.target.id==='share-date')navigate('share/'+event.target.value);
    if(event.target.id==='discovery-run')navigate('review?run='+event.target.value);
  });
  document.querySelector('#search-dialog').addEventListener('click',event=>{if(event.target===event.currentTarget){const b=event.currentTarget.getBoundingClientRect();if(event.clientX<b.left||event.clientX>b.right||event.clientY<b.top||event.clientY>b.bottom)event.currentTarget.close();}});
  function restorePosition() { const savedScroll=pageState().scroll||0; requestAnimationFrame(()=>requestAnimationFrame(()=>{const id=route().query.get('update');const target=id&&document.getElementById('entry-'+id);if(target){target.scrollIntoView({block:'start'});target.classList.add('event-target');}else window.scrollTo(0,savedScroll);})); }
  window.addEventListener('hashchange',()=>{currentKey=location.hash.slice(1)||'home';if(route().query.get('update')){pageState().tab='recent';state.opened.add(route().query.get('update'));}render();restorePosition();});
  window.addEventListener('pagehide',()=>{pageState().scroll=window.scrollY;persist();});
  let scrollTick=false;
  window.addEventListener('scroll',()=>{if(!scrollTick){scrollTick=true;requestAnimationFrame(()=>{pageState().scroll=window.scrollY;scrollTick=false;});}},{passive:true});
  if(route().query.get('update')) {pageState().tab='recent';state.opened.add(route().query.get('update'));}
  if(real){
    document.querySelector('.edition-tag').textContent=production?(production.status==='public'?'本期更新':'未公开预览'):'真实样稿';
    document.querySelector('.footer-note').innerHTML=production?`<span>陕西资本观察 / ${production.status==='public'?'每日观察':'本地预览'}</span><span>${production.status==='public'?'历史内容保留原时点。':'本期尚未公开；历史资料保留原时点。'}${publicOutput?'':'<a href="#review">发现与核查记录 ↗</a>'}</span>`:publicOutput?'<span>陕西资本观察</span><span>历史内容按其原资料时点保留。</span>':window.DISCOVERY?'<span>陕西资本观察 / 第3阶段 · 发现验收</span><span>正式样稿保留原时点。<a href="#review">发现、工作池与核查记录 ↗</a></span>':'<span>陕西资本观察 / 第二阶段 · 内容验收</span><span>有限研究，名单未更新。<a href="#review">样稿范围与暂缓记录 ↗</a></span>';
    if(production) document.querySelector('#search-dialog > .small').textContent='按名称、证券代码或登记编号查找；字段时点及依据见对象页。';
  }
  render();restorePosition();
})();
