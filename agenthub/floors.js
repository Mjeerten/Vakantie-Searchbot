/* Agent Hub floor + agent data (edit here to add or change floors/agents). Loaded before office.js. */
window.HUB_DATA=(()=>{
/* CEO routine + watcher switched off 2026-10-05; its 4F floor is now the Travel Desk (2026-11-24). */
const CEO_PAUSED=true;
const TV='#travel', FD='#flipdeck', SW='https://claude.ai/artifact/1cke8qmoKTMLRgLJUgDKo9';
const FLOORS=[
  {id:'travel',lv:'4F',knob:'4',name:'Travel Desk',sub:'1 agent · daily',
   text:'Atlas plans your summer trip for two (23 Jul - 13 Aug 2027): Japan first, South-East Asia as plan B. Every day it prices its own routes all-in per person (flights, hotels, trains, food, activities), compares package tours, and pings your phone only when a trip fits the budget.',
   facts:[['Repo','vakantie-searchbot'],['Budget','€1,500 - €2,500 p.p.']],link:{href:'#travel',label:'Open Travel Desk',hint:'Best trips, packages, settings'}},
  {id:'swing',lv:'3F',knob:'3',name:'Swing Desk',sub:'1 agent · nightly',
   text:'Your swing-trading system. Every night it screens for 10/20/50-day SMA + ADR% breakouts, reviews open trades against the 20-day trail exit and sends a report to your phone. Trading 212 access is read-only.',
   facts:[['Folder','Claude code trading']],link:{href:SW,label:'Open Swing Desk',hint:'Picks, open trades, nightly reports'}},
  {id:'tech',lv:'2F',knob:'2',name:'Flipdeck · Tech',sub:'3 agents · Marktplaats',
   text:'Gadgets, cameras and cars. Circuit and Aperture sweep Marktplaats for underpriced listings; Car Scout looks for your first car when you ask.',
   facts:[['Folder','Resell flipdeck']],link:{href:FD,label:'Open Flipdeck',hint:'Deals, agents, Scan for cars'}},
  {id:'collect',lv:'1F',knob:'1',name:'Flipdeck · Collectibles',sub:'3 agents · Marktplaats',
   text:'Skylanders, fragrances and LEGO. These agents hunt rare variants, sealed sets and niche bottles, for profit or for your own collection.',
   facts:[['Folder','Resell flipdeck']],link:{href:FD,label:'Open Flipdeck',hint:'Deals, agents, sweep log'}},
  {id:'lobby',lv:'G',knob:'G',name:'Front desk',sub:'Noor · closed while the CEO is paused',
   text:'Leave a request with Noor. The CEO picks it up at the next check and answers here, or sends it to the right floor.',
   facts:[]},
];
const FI=Object.fromEntries(FLOORS.map((f,i)=>[f.id,i]));
const P=(hue,dark)=>({shirt:hue,arm:dark});
const HID={scout:'carscout'};

const AGENTS=[
  {id:'atlas',floor:'travel',name:'Atlas',role:'Travel agent. Searches flights, hotels and package tours once a day, and right away when you press Search now.',status:'scheduled',label:'Daily search',speed:12,
   look:{skin:'#e8bd94',hair:'#3b2416',shirt:'#2f8f9b',arm:'#267680',pants:'#e2d6bd',shoes:'#5a3a22',cap:'#c9a46a'},
   st:[{x:222,face:2,act:'type',min:5,max:10},{x:168,face:2,act:'look',min:3,max:6},{x:206,face:2,act:'look',min:3,max:6},{x:106,face:2,act:'look',min:3,max:6},{x:322,face:1,act:'look',min:2,max:5}]},
  {id:'swing',floor:'swing',name:'Swing Runner',role:'Nightly routine at 22:15 Amsterdam, with a 23:15 catch-up.',status:'scheduled',label:'Nightly 22:15',speed:14,
   look:{skin:'#c68a5e',hair:'#2b1d14',shirt:'#2f7d5b',arm:'#266a4c',pants:'#2a2f3a',shoes:'#111'},
   st:[{x:105,face:2,act:'type',min:4,max:9},{x:145,face:2,act:'type',min:4,max:9},{x:185,face:2,act:'type',min:4,max:9},{x:225,face:2,act:'type',min:4,max:9},{x:306,face:2,act:'look',min:3,max:6},{x:318,face:1,act:'look',min:2,max:4}]},
  {id:'circuit',floor:'tech',name:'Circuit',role:'Consoles & tech: handhelds, consoles and premium gadgets that resell fast.',status:'scheduled',label:'Every 2 h',speed:16,
   look:{skin:'#f0c9a0',hair:'#d9a441',...P('#5fd49a','#46b07e'),pants:'#3b4a6b',shoes:'#e8e8e8'},
   st:[{x:158,face:2,act:'type',min:4,max:9},{x:90,face:2,act:'look',min:2,max:5},{x:142,face:2,act:'look',min:2,max:4}]},
  {id:'aperture',floor:'tech',name:'Aperture',role:'Cameras & lenses: mirrorless bodies and quality glass from private sellers.',status:'scheduled',label:'Every 2 h',speed:13,
   look:{skin:'#c68a5e',hair:'#3a2418',...P('#b394ff','#9478e0'),pants:'#2a2f3a',shoes:'#111'},
   st:[{x:110,face:2,act:'look',min:2,max:5},{x:172,face:2,act:'type',min:3,max:7},{x:202,face:1,act:'look',min:3,max:6}]},
  {id:'scout',floor:'tech',name:'Car Scout',role:'Finds a cheap, reliable first car near Waspik with Bluetooth. Runs only when you press Scan for cars; picks requests up at 12:00 and 20:00.',status:'onrequest',label:'On request · 12:00 + 20:00',speed:13,
   look:{skin:'#8d5a3b',hair:'#151515',shirt:'#3d7fc4',arm:'#336ba6',pants:'#2c3e57',shoes:'#111',cap:'#d1495b'},
   st:[{x:228,face:1,act:'look',min:4,max:8},{x:328,face:-1,act:'look',min:4,max:8},{x:278,face:0,act:'idle',min:3,max:6}]},
  {id:'portal',floor:'collect',name:'Portal',role:'Skylanders: rare variants, sealed figures and underpriced lots.',status:'scheduled',label:'Every hour',speed:14,
   look:{skin:'#f0c9a0',hair:'#6b3a1e',...P('#ffb34a','#e0952e'),pants:'#3b4a6b',shoes:'#111'},
   st:[{x:100,face:2,act:'look',min:3,max:7},{x:122,face:2,act:'type',min:3,max:6},{x:86,face:2,act:'look',min:2,max:5}]},
  {id:'brick',floor:'collect',name:'Brick',role:'LEGO sets: sealed and complete sets, retired themes, big collections.',status:'scheduled',label:'Every 2 h',speed:12,
   look:{skin:'#e0b48c',hair:'#151515',...P('#62d2e8','#47b4ca'),pants:'#2a2f3a',shoes:'#c0392b'},
   st:[{x:178,face:2,act:'type',min:4,max:8},{x:204,face:2,act:'type',min:3,max:7},{x:236,face:0,act:'idle',min:2,max:5}]},
  {id:'scent',floor:'collect',name:'Scent',role:'Fragrances & colognes: niche houses and high-end designer, for profit or a cheap collection pick.',status:'scheduled',label:'Every hour',speed:11,
   look:{skin:'#8d5a3b',hair:'#2a1a12',...P('#ff7eb6','#e0619a'),pants:'#1f2433',shoes:'#111'},
   st:[{x:276,face:2,act:'look',min:3,max:7},{x:304,face:2,act:'look',min:3,max:7},{x:332,face:2,act:'look',min:3,max:7}]},
  {id:'noor',floor:'lobby',name:'Noor',role:'Receptionist. The desk is closed while the CEO is paused.',status:'standby',label:'Desk closed',speed:8,lift:5,
   look:{skin:'#d9a27a',hair:'#5a2e1a',shirt:'#c9a46a',arm:'#a8864f',pants:'#2a2e3b',shoes:'#111'},
   st:[{x:212,face:0,act:'idle',min:8,max:16},{x:197,face:2,act:'type',min:4,max:8},{x:228,face:0,act:'idle',min:4,max:8}]},
];

return {TV,FD,SW,FLOORS,FI,P,HID,AGENTS,CEO_PAUSED};
})();
