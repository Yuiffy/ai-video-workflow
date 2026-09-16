/* Deterministic principle animations. No random values or wall-clock state in renderAt. */
(() => {
  const ease = x => { x = Math.max(0, Math.min(1, x)); return x*x*(3-2*x); };
  const facts = [
    ["人工把材料交给 GPT，仍要自己修改与发送。", "起点：开发者回忆"],
    ["合并复读，降低低信息内容权重。", "2024–2025 · 07e70a4 / 4e9aca6"],
    ["从随机丢弃，到评分、目标行数与必留项。", "2025.09 · 538864e / 6ab11c3"],
    ["模型能力改变后，重新试验全文输入与原文复核。", "2026.09 · ab0bbb3 · 弥月、米汀实验"],
    ["从一句万能夸奖，转向只属于今晚的细节。", "2026.08 · 8229a10"],
    ["主播、粉丝、嘉宾、时段，各有边界。", "a032780 / b96ecf4 / 4f3592a"],
    ["选事件 → 写节拍 → 排动作 → 校验脚本。", "acb82b2 / 73d77a5 / 94f6915"],
    ["立绘负责身份，截图负责本场发生的事。", "e18bb05 / 5cb7644 / 576e00c"],
    ["人设是线索，本场标题与原话才是事实。", "2026.08 · 1e3525d"],
    ["能力升级后，重新设计台词、拟声词和文字位置。", "14b59ca → 69c70db → 3ee8916"],
    ["四格讲顺序，沉浸式讲一个有中心的现场。", "2026.08 · 4fd3b52 / fb2d1de"],
    ["按房间配置，不能把所有人套成同一个模板。", "a612fff / be90835 / 77e2c44"],
    ["名字出现，不等于人物在场；同音也不等于同义。", "8dc6093 / 72a7836 / e1ec1de"],
    ["重连不下播；找到动态后，再权衡时效与等图。", "18df8d0 / 4c1d671 / 260cf0d"],
    ["排队、恢复、缓存和防重复，支撑日常稳定运行。", "067a576 / 260cf0d / c383728"],
    ["反复修正具体失败，让心意值得被收到。", "713 次提交 · 截至 81a3e82"]
  ];
  slides.forEach((slide, i) => {
    slide.querySelector("p").textContent = facts[i][0];
    slide.querySelector(".source").textContent = facts[i][1];
    slide.querySelector(".counter").textContent = "示意动画 · 实现依据见项目 sources.md";
  });
  const style = document.createElement("style");
  style.textContent = ".stage{font-size:25px}.stage .tokens{bottom:-85px}.motion-note{position:absolute;left:5%;right:5%;bottom:32px;text-align:center;color:var(--gold);font-size:25px}.motion-head{position:absolute;left:5%;top:42px;color:var(--muted);font-size:22px}.packet{font-style:normal;font-size:24px;width:155px;height:58px}.flow-destination{position:absolute;right:4%;top:40%;border:2px solid var(--cyan);padding:34px;border-radius:16px}.logic-card{position:absolute;border:1px solid #4c7e85;background:#102f38;border-radius:15px;padding:22px;color:var(--ink)}.stage svg{width:100%;height:100%;overflow:visible}.stage svg text{font-family:'Microsoft YaHei';fill:#c2dcda;font-size:23px}.stage svg .accent{fill:var(--cyan)}.script-node{font-size:23px}.script-track{top:60%}.script-dot{top:calc(60% - 13px)}.model-labels{font-size:18px;line-height:1.6;gap:20px}.model-labels span{max-width:225px}.context-box{height:230px}.glyphs{font-size:37px}.stage .rule{top:20%;bottom:auto}.goodprompt{top:55%}.badprompt{top:35%}.full-badge{background:#0b2730;top:auto;bottom:24px}.qitem{width:150px;font-size:23px}";
  document.head.appendChild(style);
  const stages = slides.map(s => s.querySelector(".stage"));
  stages[0].innerHTML = '<div class="motion-head">复制 · 粘贴 · 生成 · 人工修改</div><div class="axis"></div><div class="flow-destination">GPT 网页</div><div class="packet">弹幕</div><div class="packet">原话</div><div class="packet hot">今晚的细节</div><div class="motion-note">一段输入，换来一份草稿</div>';
  stages[7].innerHTML = '<div class="motion-head">让参考图分别承担明确任务</div><div class="logic-card" style="left:4%;top:24%;width:230px">角色立绘<br><small>发型 · 服装 · 身份</small></div><div class="logic-card" style="left:4%;top:58%;width:230px">录播截图<br><small>游戏 · 道具 · 结果</small></div><div class="logic-card" style="right:4%;top:39%;width:230px">画面脚本<br><small>谁在做什么？</small></div><svg viewBox="0 0 880 600"><path class="ref-path" d="M300 200L510 290M300 400L510 310" fill="none" stroke="#63e4cf" stroke-width="3" stroke-dasharray="300" stroke-dashoffset="300"/></svg><div class="motion-note">像这个人，也得是这场事</div>';
  stages[9].querySelector(".model-labels").innerHTML = '<span>2026.01<br>尽量少字／无字</span><span>2026.02<br>Gemini / Nano Banana<br>按能力启用中文</span><span>2026.04<br>GPT Image 2<br>规划文字和位置</span>';
  stages[10].innerHTML = '<div class="motion-head">两种构图，把同一段经历讲清楚</div><svg viewBox="0 0 880 600"><g id="panels"></g><text x="75" y="540" class="composition-label">四格：起因 → 反应 → 转折 → 结果</text></svg>';
  const panels = stages[10].querySelector("#panels");
  ["起因", "反应", "转折", "结果"].forEach((label,i) => {
    const g=document.createElementNS("http://www.w3.org/2000/svg","g");
    g.innerHTML='<rect rx="14" fill="#143943" stroke="#61bfb3"/><circle r="23" fill="#77cabb"/><path d="M-39 58 Q0 3 39 58" fill="#477b80"/><text text-anchor="middle">'+label+'</text>';
    panels.appendChild(g);
  });
  stages[12].innerHTML = '<div class="motion-head">先分清来源，再判断身份</div><div class="logic-card sticker" style="left:4%;top:22%;width:650px">[花礼收藏集表情包_哈气]</div><div class="logic-card speech" style="left:4%;top:52%;width:650px">明确原话 + 说话人证据 + 本场上下文</div><div class="motion-note">表情包 ≠ 嘉宾出场</div>';
  stages[13].innerHTML = '<div class="motion-head">下播到回复：不是一个定时器就够了</div><svg viewBox="0 0 880 600"><path d="M55 240H815" stroke="#315c68" stroke-width="4"/><circle id="time-cursor" cx="55" cy="240" r="12" fill="#63e4cf"/><g><text x="45" y="195">断流</text><text x="235" y="195">重连</text><text x="410" y="195">真正下播</text><text x="675" y="195">新动态</text></g><text id="time-state" x="65" y="360" class="accent">等待重连，先不发</text><text id="time-detail" x="65" y="425">避免开播几分钟就说晚安</text></svg>';
  const old = window.renderAt;
  let manual = false;
  const apply = v => {
    old(v);
    const s=stages[v.slide], p=Math.max(0,Math.min(1,v.time/Math.max(v.duration,.1)));
    const smooth=ease(p), phase=Math.min(3,Math.floor(p*4));
    s.querySelectorAll(".fill").forEach(e=>e.style.width=(Math.min(1,p*1.5)*100)+"%");
    s.querySelectorAll(".node").forEach((e,i)=>e.classList.toggle("on",p>(i+1)/5));
    s.querySelectorAll(".evidence").forEach(e=>e.style.opacity=ease((p-.2)*2));
    const note=s.querySelector(".motion-note");
    if(v.slide===0){
      s.querySelectorAll(".packet").forEach((e,i)=>{
        const t=ease((p-i*.12)*1.6);
        e.style.left=(10+61*t)+"%";e.style.top=(28+i*19+(50-28-i*19)*t)+"%";
        e.style.opacity=1-.9*ease((t-.8)*5);
      });
      note.style.opacity=ease((p-.45)*3);
    }
    if(v.slide===3){s.querySelector(".full-badge").style.opacity=ease((p-.6)*3);}
    if(v.slide===7){s.querySelector(".ref-path").style.strokeDashoffset=300*(1-smooth);}
    if(v.slide===8){s.querySelector(".film").style.opacity=ease((p-.45)*2);}
    if(v.slide===9){s.querySelectorAll(".glyphs span").forEach((e,i)=>e.style.opacity=.15+.85*ease((p-i*.25)*3));}
    if(v.slide===10){
      const t=ease((p-.25)*1.6);
      [...panels.children].forEach((g,i)=>{
        const from=[75+(i%2)*345,75+Math.floor(i/2)*205,325,185];
        const to=i===0?[60,75,755,410]:[410+(i-1)*135,325,125,145];
        const a=from.map((value,k)=>value+(to[k]-value)*t);
        const r=g.querySelector("rect");["x","y","width","height"].forEach((k,j)=>r.setAttribute(k,a[j]));
        const cx=a[0]+a[2]*.5,cy=a[1]+a[3]*.32;
        g.querySelector("circle").setAttribute("cx",cx);g.querySelector("circle").setAttribute("cy",cy);
        g.querySelector("path").setAttribute("transform","translate("+cx+" "+cy+")");
        const txt=g.querySelector("text");txt.setAttribute("x",cx);txt.setAttribute("y",a[1]+a[3]-.07*a[3]);
      });
      s.querySelector(".composition-label").textContent=p>.7?"沉浸式：主画面 + 事件节拍 + 中文回忆锚点":"四格：起因 → 反应 → 转折 → 结果";
    }
    if(v.slide===12){
      s.querySelector(".sticker").style.borderColor=p>.3?"#ff7f96":"#4c7e85";
      s.querySelector(".sticker").style.opacity=1-.65*ease((p-.25)*2);
      s.querySelector(".speech").style.opacity=.2+.8*ease((p-.4)*2);
      note.textContent=p>.7?"有可靠证据，才允许人物进入漫画":"表情包 ≠ 嘉宾出场";
    }
    if(v.slide===13){
      s.querySelector("#time-cursor").setAttribute("cx",55+760*smooth);
      s.querySelector("#time-state").textContent=["等待重连，先不发","重连成功 → 取消提前结算","真正下播 → 核对目标动态","新动态 5 分钟内 → 及时回复"][phase];
      s.querySelector("#time-detail").textContent=["避免开播几分钟就说晚安","把后续录播继续接回这一场","文件稳定、生成内容、确认时机","图未好先发文字；错过窗口则有限等图"][phase];
    }
    if(v.slide===14){s.querySelectorAll(".qitem").forEach((e,i)=>e.style.transform="translateY("+(-14*ease((p-i*.2)*3))+"px)");}
    if(v.slide===15){s.querySelector(".end-ring").style.transform="scale("+(0.88+.12*smooth)+")";s.querySelector(".end-ring").style.opacity=.25+.75*smooth;}
  };
  window.renderAt=v=>{manual=true;apply(v)};
  let began=performance.now();
  addEventListener("keydown",()=>{began=performance.now();manual=false});
  const tick=now=>{if(!manual)apply({slide:current,time:Math.min(15,(now-began)/1000),duration:15});requestAnimationFrame(tick)};
  requestAnimationFrame(tick);
})();
