(() => {
const W=400,H=360,ROOF=24,FH=64,IN0=70,IN1=356;
const RM=matchMedia('(prefers-reduced-motion: reduce)').matches;
const top=i=>ROOF+i*FH, feet=i=>ROOF+i*FH+FH-5;
const {TV,FD,SW,FLOORS,FI,HID,AGENTS,CEO_PAUSED}=window.HUB_DATA;

/* ---------- helpers ---------- */
const cv=document.getElementById('cv'), g=cv.getContext('2d');
const stc=document.createElement('canvas'); stc.width=W; stc.height=H; const s=stc.getContext('2d');
function R(c,col,x,y,w,h){c.fillStyle=col;c.fillRect(x,y,w,h);}
let seed=7; const rnd=()=>((seed=(seed*16807)%2147483647)/2147483647);
const rand=(a,b)=>a+Math.random()*(b-a);
function circ(c,col,cx,cy,r){c.fillStyle=col;for(let dy=-r;dy<=r;dy++)for(let dx=-r;dx<=r;dx++)if(dx*dx+dy*dy<=r*r+r*.6)c.fillRect(cx+dx,cy+dy,1,1);}
function line(c,col,x0,y0,x1,y1){c.fillStyle=col;let dx=Math.abs(x1-x0),sx=x0<x1?1:-1,dy=-Math.abs(y1-y0),sy=y0<y1?1:-1,e=dx+dy;for(;;){c.fillRect(x0,y0,1,1);if(x0===x1&&y0===y1)break;const e2=2*e;if(e2>=dy){e+=dy;x0+=sx}if(e2<=dx){e+=dx;y0+=sy}}}
const FONT={A:'010101111101101',B:'110101110101110',C:'011100100100011',D:'110101101101110',E:'111100110100111',F:'111100110100100',G:'011100101101011',H:'101101111101101',I:'111010010010111',J:'001001001101010',K:'101101110101101',L:'100100100100111',M:'101111111101101',N:'110101101101101',O:'010101101101010',P:'110101110100100',Q:'010101101110011',R:'110101110101101',S:'011100010001110',T:'111010010010010',U:'101101101101111',V:'101101101101010',W:'101101111111101',X:'101101010101101',Y:'101101010010010',Z:'111001010100111','0':'111101101101111','1':'010110010010111','2':'110001010100111','3':'110001010001110','4':'101101111001001'};
function ptext(c,str,x,y,col,sc=1){c.fillStyle=col;let cx=x;for(const ch of str){const gl=FONT[ch];if(gl)for(let i=0;i<15;i++)if(gl[i]==='1')c.fillRect(cx+(i%3)*sc,y+Math.floor(i/3)*sc,sc,sc);cx+=4*sc;}}
const tw=(str,sc=1)=>(str.length*4-1)*sc;

/* ---------- sky ---------- */
function skyFor(h){
  if(h>=21||h<5) return {k:'night',a:'#060a1c',b:'#1b2448',city:'#0e1328',win:'#f3d27a',night:1};
  if(h<8) return {k:'dawn',a:'#27305e',b:'#e3906c',city:'#2a2440',win:'#f3d27a',night:.5};
  if(h<18) return {k:'day',a:'#4f97d0',b:'#bfe0f0',city:'#7b8ea3',win:'#cfe3f0',night:0};
  return {k:'dusk',a:'#2a2457',b:'#e0745a',city:'#231c3a',win:'#f3d27a',night:.6};
}
let sky=skyFor(new Date().getHours());
const STARS=[];for(let i=0;i<70;i++){const x=Math.floor(Math.random()*W),y=Math.floor(Math.random()*120);if(x>36&&x<364&&y>=18)continue;STARS.push({x,y,p:Math.random()*6});}

/* ---------- static layer ---------- */
function buildStatic(){
  seed=7;
  const gr=s.createLinearGradient(0,0,0,H);gr.addColorStop(0,sky.a);gr.addColorStop(1,sky.b);s.fillStyle=gr;s.fillRect(0,0,W,H);
  // distant towers left and right
  for(const b of [{x:0,w:16,h:190},{x:14,w:24,h:130},{x:362,w:18,h:150},{x:378,w:22,h:210}]){
    R(s,sky.city,b.x,344-b.h,b.w,b.h);
    for(let y=344-b.h+4;y<340;y+=5)for(let x=b.x+2;x<b.x+b.w-2;x+=4)if(rnd()<(sky.night?.35:.15))R(s,sky.win,x,y,2,2);
  }
  // building shell
  R(s,'#3d2e2a',38,20,324,324);
  for(let y=22;y<344;y+=4){R(s,'#33261f',38,y,6,1);R(s,'#33261f',356,y,6,1);}
  // roof
  R(s,'#4b4f58',36,19,328,5);R(s,'#6b707b',36,19,328,1);
  R(s,'#3a3e47',66,17,2,3);R(s,'#3a3e47',82,17,2,3);R(s,'#6b5a4a',62,6,26,11);R(s,'#57493c',62,9,26,1);R(s,'#57493c',62,13,26,1);R(s,'#7d6a58',62,6,26,1);
  R(s,'#3a3e47',156,15,2,4);R(s,'#3a3e47',242,15,2,4);
  R(s,'#2a2e38',128,3,144,13);R(s,'#12141b',129,4,142,11);
  ptext(s,'AGENT HUB',200-tw('AGENT HUB',2)/2,5,'#ffcf6b',2);
  R(s,'#7a7f88',329,1,1,19);R(s,'#7a7f88',326,8,7,1);R(s,'#7a7f88',327,13,5,1);
  // floors
  FLOORS.forEach((f,i)=>{
    const t=top(i),ft=feet(i);
    R(s,'#5d6068',38,t,324,3);R(s,'#7a7d86',38,t,324,1);
    DRAW[f.id](t,ft);
    R(s,'#101218',44,t+3,24,FH-3);R(s,'#1e222b',46,t+3,1,FH-3);R(s,'#1e222b',65,t+3,1,FH-3);
    R(s,'#4a4d55',68,t+3,2,FH-3);
  });
  // street
  R(s,'#2b2d33',0,344,W,16);R(s,'#4a4d55',0,344,W,1);
  for(let x=4;x<W;x+=22)R(s,'#3a3c43',x,352,10,1);
  R(s,'#3b3e46',19,300,2,44);R(s,'#3b3e46',15,298,10,2);R(s,'#3b3e46',380,300,2,44);R(s,'#3b3e46',376,298,10,2);
}
const DRAW={
  travel(t,f){
    R(s,'#1d3138',IN0,t+3,IN1-IN0,f-t-3);
    for(let x=IN0+12;x<IN1;x+=24)R(s,'#22393f',x,t+3,1,f-t-3);
    R(s,'#16262b',IN0,f-12,IN1-IN0,1);
    R(s,'#6b4f37',IN0,f,IN1-IN0,5);R(s,'#83634a',IN0,f,IN1-IN0,1);for(let x=IN0+18;x<IN1;x+=28)R(s,'#5a4230',x,f+1,1,4);
    // departures board (rows are drawn live)
    R(s,'#c9a46a',149,t+7,152,29);R(s,'#0b0d10',150,t+8,150,27);
    ptext(s,'DEPARTURES',225-tw('DEPARTURES')/2,t+10,'#c9a46a');R(s,'#2a2a22',152,t+16,146,1);
    R(s,'#3a3e47',170,t+3,1,4);R(s,'#3a3e47',280,t+3,1,4);
    // world map with a pin on Japan
    R(s,'#e9e2cf',77,t+9,62,30);R(s,'#2b5d80',78,t+10,60,28);
    const land=[[81,14,9,6],[84,20,6,9],[87,29,4,5],[99,13,6,5],[100,19,6,10],[106,12,16,8],[110,20,10,5],[116,27,4,3],[124,30,9,5],[126,16,2,3]];
    for(const [x,y,w,h] of land){R(s,'#6aa84f',x,t+y,w,h);R(s,'#8cbf5a',x,t+y,w,1);}
    R(s,'#c0392b',127,t+15,2,2);R(s,'#7a1f17',128,t+17,1,2);
    // globe
    R(s,'#6b4a2a',121,f-6,2,6);R(s,'#6b4a2a',117,f-1,10,1);circ(s,'#3f7cac',122,f-12,4);R(s,'#6aa84f',120,f-14,3,2);R(s,'#6aa84f',123,f-11,2,3);R(s,'#c9a46a',117,f-12,1,1);R(s,'#c9a46a',127,f-12,1,1);
    // desk with laptop and brochures
    R(s,'#8a5a34',206,f-11,44,1);R(s,'#6b4428',206,f-10,44,1);R(s,'#553620',208,f-9,40,9);R(s,'#4a2e1b',228,f-8,1,7);
    R(s,'#2a2d33',216,f-13,15,2);
    R(s,'#d1495b',236,f-13,5,2);R(s,'#62d2e8',241,f-14,4,3);R(s,'#ffcf6b',237,f-15,3,2);
    // suitcases
    R(s,'#b5473a',296,f-14,11,14);R(s,'#c95a4a',296,f-14,11,1);R(s,'#7a2b22',301,f-16,1,2);R(s,'#7a2b22',299,f-17,5,1);R(s,'#e9e2cf',298,f-9,3,3);R(s,'#111',297,f,2,1);R(s,'#111',304,f,2,1);
    R(s,'#3b6a8c',310,f-19,9,19);R(s,'#4d7fa3',310,f-19,9,1);R(s,'#2a4d66',314,f-23,1,4);R(s,'#2a4d66',312,f-24,5,1);R(s,'#ffcf6b',312,f-12,3,2);R(s,'#62d2e8',315,f-7,2,2);
    // poster: Fuji
    R(s,'#c9a46a',326,t+11,22,17);R(s,'#bfe0f0',327,t+12,20,15);R(s,'#5b6f8a',330,t+19,14,8);R(s,'#5b6f8a',333,t+16,8,4);R(s,'#f4f4f4',335,t+16,4,2);R(s,'#c0392b',341,t+13,3,3);
    // plant
    R(s,'#8a5a34',340,f-6,9,6);R(s,'#2f6a3a',341,f-14,2,8);R(s,'#3f8a4a',338,f-17,4,6);R(s,'#3f8a4a',345,f-15,4,7);R(s,'#2f6a3a',343,f-19,3,6);
  },
  swing(t,f){
    R(s,'#18262a',IN0,t+3,IN1-IN0,f-t-3);R(s,'#1f3236',IN0,t+40,IN1-IN0,1);
    R(s,'#262b33',IN0,f,IN1-IN0,5);R(s,'#353b45',IN0,f,IN1-IN0,1);
    for(let k=0;k<4;k++){const mx=92+k*40,my=f-27;R(s,'#0b0e12',mx,my,26,15);R(s,'#0b0e12',mx+12,my+15,2,f-11-(my+15));}
    R(s,'#4a5563',84,f-11,168,2);R(s,'#323a45',86,f-9,164,9);for(let x=126;x<250;x+=40)R(s,'#2a3039',x,f-8,1,7);
    R(s,'#0b0e12',264,t+8,82,27);
    R(s,'#d8dde3',326,f-16,10,16);R(s,'#b9c0c8',326,f-8,10,1);R(s,'#7cc6e8',328,f-24,6,8);R(s,'#5aa8cf',328,f-20,6,1);R(s,'#3b78c4',330,f-12,2,2);
    // world clocks
    circ(s,'#d8dde3',118,t+13,5);circ(s,'#f4f1ea',118,t+13,4);circ(s,'#d8dde3',158,t+13,5);circ(s,'#f4f1ea',158,t+13,4);
    ptext(s,'AMS',118-tw('AMS')/2,t+21,'#8fb3b0');ptext(s,'NY',158-tw('NY')/2,t+21,'#8fb3b0');
  },
  tech(t,f){
    R(s,'#3b2c22',IN0,t+3,IN1-IN0,f-t-3);
    for(let y=t+3,r=0;y<f;y+=4,r++){R(s,'#2f231b',IN0,y,IN1-IN0,1);for(let x=IN0+(r%2?5:0);x<IN1;x+=10)R(s,'#2f231b',x,y,1,4);}
    R(s,'#4b4b4f',IN0,f,IN1-IN0,5);R(s,'#5e5e63',IN0,f,IN1-IN0,1);
    // garage door
    R(s,'#2a2f36',224,t+7,124,f-t-7);for(let y=t+8;y<f;y+=3)R(s,y%2?'#56606b':'#4a535d',226,y,120,2);
    R(s,'#3a3a3e',262,f+1,26,2);
    // tech shelves: game boy, switch, console, camera, lenses, drone
    R(s,'#8792a0',76,t+10,2,f-t-10);R(s,'#8792a0',121,t+10,2,f-t-10);
    for(const y of [t+22,t+36,f-10])R(s,'#8792a0',76,y,47,1);
    R(s,'#c8c4bc',80,t+13,7,9);R(s,'#7f9a5a',81,t+14,5,3);R(s,'#2a2a2a',81,t+19,2,1);R(s,'#a03060',85,t+19,1,1);
    R(s,'#1e1e22',93,t+17,12,5);R(s,'#2a8fd0',91,t+17,2,5);R(s,'#e0453a',105,t+17,2,5);R(s,'#3a5a7a',95,t+18,8,3);
    R(s,'#3a3d44',110,t+15,9,7);R(s,'#5c6068',110,t+15,9,1);
    R(s,'#1b1c20',80,t+29,11,7);R(s,'#1b1c20',82,t+27,4,2);circ(s,'#2c2f36',86,t+32,2);R(s,'#7a8cff',86,t+32,1,1);R(s,'#c0392b',89,t+30,1,1);
    R(s,'#222',95,t+30,5,6);R(s,'#c0392b',95,t+31,5,1);R(s,'#222',102,t+32,4,4);R(s,'#3a3d44',108,t+28,10,8);R(s,'#5fd49a',110,t+30,6,1);
    R(s,'#55595f',82,f-14,14,2);R(s,'#2a2d33',80,f-15,2,1);R(s,'#2a2d33',96,f-15,2,1);R(s,'#2a2d33',87,f-12,4,2);R(s,'#b98a52',100,f-17,18,7);R(s,'#d9b27c',108,f-17,2,7);
    // pinboard + desk
    R(s,'#6d4c2f',131,t+9,56,21);R(s,'#a9784a',132,t+10,54,19);
    for(const [x,y,c] of [[135,12,'#5fd49a'],[144,15,'#b394ff'],[154,11,'#9bd1e5'],[163,16,'#5fd49a'],[173,12,'#f6f1e4'],[139,21,'#b394ff'],[160,21,'#d1495b'],[176,21,'#f4d35e']]){R(s,c,x,t+y,7,6);R(s,'#c0392b',x+3,t+y,1,1);}
    R(s,'#7a8693',136,f-11,50,2);R(s,'#5c6672',138,f-9,2,9);R(s,'#5c6672',182,f-9,2,9);
    R(s,'#1a1a1a',150,f-20,17,9);R(s,'#9aa3ad',148,f-12,21,1);
    // tripod + camera
    line(s,'#2a2d33',210,f-1,213,f-14);line(s,'#2a2d33',216,f-1,213,f-14);R(s,'#2a2d33',213,f-14,1,13);
    R(s,'#1b1c20',209,f-19,9,5);R(s,'#1b1c20',211,f-21,3,2);circ(s,'#2c2f36',219,f-17,2);R(s,'#b394ff',219,f-17,1,1);
    // car
    const cy=f-14;
    R(s,'#2f2f33',238,f,80,1);
    R(s,'#d1495b',238,cy,78,1);R(s,'#d1495b',236,cy+1,82,7);R(s,'#a33545',236,cy+7,82,1);
    for(let r=0;r<8;r++){const xs=252-(r>5?1:0),xe=288+r*2;R(s,'#d1495b',xs,cy-8+r,xe-xs,1);if(r>0&&r<7)R(s,'#a8dadc',xs+3,cy-8+r,xe-xs-6,1);}
    R(s,'#d1495b',272,cy-7,2,7);R(s,'#c9eef0',257,cy-6,2,1);
    R(s,'#ffe9a8',316,cy+2,2,2);R(s,'#7a0f1f',236,cy+2,2,2);R(s,'#3a3a3e',236,cy+6,5,2);R(s,'#3a3a3e',313,cy+6,5,2);R(s,'#a33545',275,cy+3,6,1);
    circ(s,'#141414',254,f-4,4);circ(s,'#141414',300,f-4,4);circ(s,'#b8c0c8',254,f-4,1);circ(s,'#b8c0c8',300,f-4,1);
  },
  collect(t,f){
    R(s,'#2a2233',IN0,t+3,IN1-IN0,f-t-3);for(let x=IN0+3;x<IN1;x+=6)R(s,'#30263b',x,t+3,2,f-t-3);
    R(s,'#221b2a',IN0,f-12,IN1-IN0,1);
    R(s,'#6b5440',IN0,f,IN1-IN0,5);R(s,'#7d6450',IN0,f,IN1-IN0,1);for(let x=IN0+7,k=0;x<IN1;x+=18,k++)R(s,'#5a4535',x,f+1+(k%2)*2,1,2);
    // Skylanders wall shelf
    const fc=['#ff7a3a','#3fb0ff','#7ad04a','#c070ff','#ffd24a','#ff4a6a','#4ae0d0'];
    for(const y of [t+17,t+28,t+39]){R(s,'#5b3a24',78,y,62,2);for(let x=80;x<136;x+=6){const c=fc[Math.floor(rnd()*fc.length)];R(s,c,x+1,y-5,3,4);R(s,c,x,y-4,1,2);R(s,c,x+4,y-4,1,2);R(s,'#f0e0c8',x+2,y-5,1,1);R(s,'#222',x,y-1,5,1);}}
    // portal table
    R(s,'#5b3a24',90,f-9,40,2);R(s,'#47301e',92,f-7,2,7);R(s,'#47301e',126,f-7,2,7);
    R(s,'#9aa3ad',99,f-11,16,2);R(s,'#d8dde3',100,f-12,14,1);
    R(s,'#3fb0ff',120,f-14,3,4);R(s,'#3fb0ff',119,f-13,1,2);R(s,'#3fb0ff',123,f-13,1,2);R(s,'#222',119,f-10,5,1);
    // LEGO table, build and boxes
    R(s,'#e9e2cf',166,f-10,54,2);R(s,'#bdb6a4',168,f-8,2,8);R(s,'#bdb6a4',216,f-8,2,8);
    const bk=['#d01012','#f2c230','#0b62b5','#237841'];
    for(let r=0;r<6;r++){const w=24-r*3,x0=176+Math.floor(r*1.5);for(let x=x0;x<x0+w;x+=4){R(s,bk[Math.floor(rnd()*4)],x,f-12-r*2,4,2);}}
    for(const [x,c] of [[170,'#f2c230'],[204,'#0b62b5'],[210,'#d01012'],[214,'#237841']])R(s,c,x,f-11,3,1);
    for(const [y,h] of [[f-22,11],[f-11,11]]){R(s,'#f2c230',224,y,24,h);R(s,'#d01012',225,y+1,4,4);R(s,'#3b78c4',231,y+2,15,h-4);R(s,'#e8eef4',233,y+4,4,3);}
    R(s,'#0b62b5',228,f-32,18,10);R(s,'#d01012',229,f-31,4,4);R(s,'#f2c230',235,f-29,9,5);
    // perfume cabinet
    R(s,'#c9a46a',261,t+7,86,f-t-7);R(s,'#1a1520',263,t+9,82,f-t-9);
    const gr=s.createLinearGradient(0,t+9,0,f);gr.addColorStop(0,'rgba(255,214,170,.18)');gr.addColorStop(1,'rgba(255,214,170,0)');s.fillStyle=gr;s.fillRect(263,t+9,82,f-t-9);
    R(s,'#c9a46a',290,t+9,1,f-t-9);R(s,'#c9a46a',318,t+9,1,f-t-9);
    const pc=['#e0a040','#ff9ec8','#cfe6ee','#6a4a8a','#f2d27a','#9fe0c8','#c0392b','#2a2a34'];
    for(const y of [t+22,t+36,f-10]){R(s,'#9fb7c4',263,y,82,1);
      for(const [x0,x1] of [[265,289],[292,317],[320,344]]){for(let x=x0;;){const w=3+Math.floor(rnd()*3),h=4+Math.floor(rnd()*4);if(x+w>x1)break;const c=pc[Math.floor(rnd()*pc.length)];
        R(s,c,x,y-h,w,h);R(s,'rgba(255,255,255,.35)',x,y-h,1,h);R(s,'#c9a46a',x+(w>>1),y-h-2,1,2);if(rnd()<.5)R(s,'#2a2a2a',x+(w>>1)-1,y-h-3,3,1);x+=w+2+Math.floor(rnd()*2);}}}
  },
  lobby(t,f){
    R(s,'#2a2e3b',IN0,t+3,IN1-IN0,f-t-3);for(const x of [150,262])R(s,'#323748',x,t+3,8,f-t-3);
    for(let x=IN0;x<IN1;x+=6)for(let y=0;y<5;y++)R(s,((x/6|0)+y)%2?'#cfc8b8':'#b4ad9e',x,f+y,6,1);R(s,'#e2dccd',IN0,f,IN1-IN0,1);
    // directory board
    R(s,'#c9a46a',83,t+16,58,38);R(s,'#14161c',84,t+17,56,36);
    ptext(s,'DIRECTORY',112-tw('DIRECTORY')/2,t+19,'#c9a46a');R(s,'#3a3424',88,t+25,48,1);
    [['4','TRAVEL'],['3','SWING'],['2','TECH'],['1','COLLECT']].forEach(([n,l],k)=>{ptext(s,n,89,t+28+k*6,'#ffcf6b');ptext(s,l,97,t+28+k*6,'#e9e2cf');});
    // reception
    R(s,'#c9a46a',180,f-13,64,1);R(s,'#5d4632',181,f-12,62,12);for(let x=184;x<242;x+=8)R(s,'#6d5440',x,f-11,4,10);
    R(s,'#14161c',201,f-9,22,7);ptext(s,'INFO',212-tw('INFO')/2,f-8,'#c9a46a');
    R(s,'#c9a46a',236,f-15,3,2);R(s,'#111',192,f-19,10,6);R(s,'#111',196,f-14,2,1);
    // plants
    for(const px of [168,292]){R(s,'#cfc8b8',px-4,f-7,9,7);R(s,'#a39c8c',px-4,f-7,9,1);R(s,'#2f6a3a',px-1,f-20,2,13);R(s,'#3f8a4a',px-5,f-22,4,9);R(s,'#3f8a4a',px+2,f-24,4,10);R(s,'#2f6a3a',px-2,f-26,4,6);}
    // door
    R(s,'#8f9aa6',318,t+10,36,f-t-10);R(s,'#2b4258',320,t+12,15,f-t-12);R(s,'#2b4258',337,t+12,15,f-t-12);
    line(s,'#4d6a86',322,t+30,332,t+16);line(s,'#4d6a86',339,t+34,349,t+20);
    R(s,'#d6dde4',333,f-26,1,8);R(s,'#d6dde4',339,f-26,1,8);R(s,'#5a3a2a',314,f,40,1);
  }
};

/* ---------- live props ---------- */
const mons=[0,1,2,3].map(()=>{let v=.5;const a=[];for(let i=0;i<8;i++){const o=v;v=Math.min(.95,Math.max(.05,v+rand(-.18,.2)));a.push({o,c:v,h:Math.max(o,v)+rand(0,.08),l:Math.min(o,v)-rand(0,.08)});}return a;});
let wall=[];{let v=.5;for(let i=0;i<80;i++){v=Math.min(.95,Math.max(.05,v+rand(-.07,.075)));wall.push(v);}}
const lift={i:4,y:feet(4)-22,target:4,wait:2};
let tick=0,monT=0,wallT=0;

function drawLive(t){
  const tw_=sky.night;
  if(tw_)for(const st of STARS){const a=.35+.65*Math.abs(Math.sin(t*.6+st.p));g.fillStyle=`rgba(255,248,225,${(a*tw_).toFixed(2)})`;g.fillRect(st.x,st.y,1,1);}
  if(Math.floor(t*1.2)%2===0){R(g,'#ff4b4b',328,0,3,2);}
  if(sky.night>.4){for(const lx of [20,381]){g.fillStyle='rgba(255,226,150,.12)';g.beginPath();g.moveTo(lx-3,301);g.lineTo(lx-14,344);g.lineTo(lx+14,344);g.lineTo(lx+3,301);g.fill();R(g,'#ffe2a0',lx-3,300,6,1);}}
  // travel desk: departures board + laptop
  {const T=top(FI.travel),F=feet(FI.travel);const rows=[['TOKYO','GATE 2'],['OSAKA','GATE 4'],['HANOI','GATE 1'],['BANGKOK','GATE 3']];const base=Math.floor(t/5)%rows.length;
   for(let k=0;k<3;k++){const [c,gt]=rows[(base+k)%rows.length],y=T+18+k*6,lead=k===0;ptext(g,c,153,y,lead?'#ffcf6b':'#d6c9a0');const st=lead?(Math.floor(t*2)%2?'BOARDING':''):gt;if(st)ptext(g,st,297-tw(st),y,lead?'#5fd49a':'#8b93a7');}
   R(g,'#1b2b4a',217,F-20,13,7);R(g,'#62d2e8',218,F-19,6,1);R(g,'#ffcf6b',218,F-17,9,1);if(Math.floor(t*2)%2)R(g,'#cfe0ff',228,F-17,1,1);}
  // swing monitors
  {const F=feet(1),T=top(1);
   mons.forEach((a,k)=>{const mx=93+k*40,my=F-26;R(g,'#06170f',mx,my,24,13);a.forEach((c,j)=>{const y=v=>my+1+Math.round((1-v)*11);const up=c.c>=c.o,col=up?'#3ddc97':'#ff5d73';R(g,col,mx+j*3+1,y(c.h),1,Math.max(1,y(c.l)-y(c.h)));const yt=y(Math.max(c.o,c.c)),yb=y(Math.min(c.o,c.c));R(g,col,mx+j*3,yt,3,Math.max(1,yb-yt));});});
   R(g,'#06170f',265,T+9,80,25);for(let x=0;x<80;x++){const y=T+10+Math.round((1-wall[x])*22);R(g,'rgba(61,220,151,.18)',265+x,y+1,1,T+34-y-1);R(g,'#3ddc97',265+x,y,1,1);}
   R(g,'#ffcf6b',344,T+10+Math.round((1-wall[79])*22),1,1);
   const now=new Date();
   const hm=tz=>{const p=new Intl.DateTimeFormat('en-GB',{timeZone:tz,hour:'numeric',minute:'numeric',hour12:false}).formatToParts(now);return [+p.find(x=>x.type==='hour').value,+p.find(x=>x.type==='minute').value];};
   [[118,'Europe/Amsterdam'],[158,'America/New_York']].forEach(([cx,tz])=>{let h,m;try{[h,m]=hm(tz)}catch(e){h=now.getHours();m=now.getMinutes();}
     const am=m/60*Math.PI*2-Math.PI/2,ah=((h%12)+m/60)/12*Math.PI*2-Math.PI/2;
     line(g,'#1a1d24',cx,T+13,cx+Math.round(Math.cos(ah)*2),T+13+Math.round(Math.sin(ah)*2));
     line(g,'#c0392b',cx,T+13,cx+Math.round(Math.cos(am)*3),T+13+Math.round(Math.sin(am)*3));});
  }
  // tech laptop
  {const F=feet(2);R(g,'#0f1b2b',151,F-19,15,7);const off=Math.floor(t*3)%6;for(let r=0;r<4;r++){const y=F-19+((r*2+6-off)%8);if(y>=F-19&&y<F-12){R(g,r%2?'#5fd49a':'#b394ff',152,y,3,1);R(g,'#5f7a99',156,y,8-(r%3)*2,1);}}}
  // portal of power + perfume glints
  {const F=feet(3),T=top(3);const pu=.6+.4*Math.sin(t*2.4);const gr=g.createRadialGradient(107,F-13,1,107,F-13,20);gr.addColorStop(0,`rgba(255,179,74,${(.45*pu).toFixed(3)})`);gr.addColorStop(1,'rgba(255,179,74,0)');g.fillStyle=gr;g.fillRect(85,F-33,44,24);
   R(g,pu>.7?'#ffe0a0':'#ffb34a',101,F-12,12,1);
   const k=Math.floor(t*1.7);for(let i=0;i<3;i++){const h=(Math.abs(Math.sin(k*12.9898+i*78.233))*43758.5453)%1,h2=(Math.abs(Math.sin(k*39.346+i*11.135))*24634.6345)%1;R(g,'#fff6e0',266+Math.floor(h*76),T+12+Math.floor(h2*(F-T-14)),1,1);}}
  // elevator
  R(g,'#2a2d33',56,24,1,Math.max(0,lift.y-24));
  {const y=Math.round(lift.y);R(g,'#c9a46a',46,y,20,22);R(g,'#f2e3b6',47,y+2,18,19);R(g,'#e6d39c',47,y+2,18,1);R(g,'#8a6d3b',46,y+21,20,1);R(g,'#ffcf6b',55,y,2,1);}
}

/* ---------- agents ---------- */
for(const a of AGENTS){a.fi=FI[a.floor];const s0=a.st[Math.floor(Math.random()*a.st.length)];a.cur=s0;a.x=s0.x;a.state='act';a.dir=s0.face;a.timer=rand(1,4);a.anim=Math.random()*3;a.blink=rand(2,5);}
function pick(a){const opts=a.st.filter(s=>s!==a.cur);a.cur=opts[Math.floor(Math.random()*opts.length)];a.state='walk';}
function upd(a,dt){
  a.anim+=dt;a.blink-=dt;if(a.blink<-.14)a.blink=rand(2,6);
  if(a.state==='walk'){const d=a.cur.x-a.x,step=a.speed*dt;if(Math.abs(d)<=step){a.x=a.cur.x;a.state='act';a.dir=a.cur.face;a.timer=rand(a.cur.min,a.cur.max);}else{a.x+=Math.sign(d)*step;a.dir=Math.sign(d);}}
  else{a.timer-=dt;if(a.timer<=0)pick(a);}
}
function drawAgent(a){
  const L=a.look,x=Math.round(a.x),fy=feet(a.fi)-(a.lift||0),y=fy-14,d=a.dir,walk=a.state==='walk',fr=walk?Math.floor(a.anim/.16)%2:0;
  if(!a.lift){g.fillStyle='rgba(0,0,0,.35)';g.fillRect(x-3,fy,7,1);}
  if(!fr){R(g,L.pants,x-2,y+10,2,3);R(g,L.pants,x+1,y+10,2,3);R(g,L.shoes,x-2,y+13,2,1);R(g,L.shoes,x+1,y+13,2,1);}
  else{R(g,L.pants,x-2,y+10,5,1);R(g,L.pants,x-3,y+11,2,2);R(g,L.pants,x+2,y+11,2,2);R(g,L.shoes,x-3,y+13,2,1);R(g,L.shoes,x+2,y+13,2,1);}
  R(g,L.shirt,x-2,y+5,5,5);
  const typing=a.state==='act'&&a.cur.act==='type';
  if(typing){const b=Math.floor(a.anim*7)%2;R(g,L.arm,x-3,y+5,1,3);R(g,L.arm,x+3,y+5,1,3);R(g,L.skin,x-3,y+7+b,1,1);R(g,L.skin,x+3,y+8-b,1,1);}
  else{const sw=walk?(fr?1:-1):0;R(g,L.arm,x-3,y+5,1,4);R(g,L.arm,x+3,y+5,1,4);R(g,L.skin,x-3,y+9+(sw>0?-1:0),1,1);R(g,L.skin,x+3,y+9+(sw<0?-1:0),1,1);}
  if(L.tie&&d!==2){R(g,'#ece8df',x,y+5,1,1);R(g,L.tie,x,y+6,1,3);}
  R(g,L.skin,x-2,y+1,5,4);
  if(d===2){R(g,L.hair,x-2,y,5,4);}
  else{R(g,L.hair,x-2,y,5,2);if(d===1)R(g,L.hair,x-2,y+2,1,2);else if(d===-1)R(g,L.hair,x+2,y+2,1,2);else{R(g,L.hair,x-2,y+2,1,1);R(g,L.hair,x+2,y+2,1,1);}
    if(a.blink>0){if(d===0){R(g,'#141414',x-1,y+3,1,1);R(g,'#141414',x+1,y+3,1,1);}else R(g,'#141414',x+d,y+3,1,1);}}
  if(L.cap){R(g,L.cap,x-2,y,5,2);if(d===1||d===-1)R(g,L.cap,x+3*d,y+1,1,1);else if(d===0)R(g,L.cap,x-1,y+2,3,0);}
}

/* ---------- overlay ---------- */
const ov=document.getElementById('ov');
let selFloor='travel',selAgent=null;
const plates=FLOORS.map((f,i)=>{const b=document.createElement('button');b.type='button';b.className='plate';b.style.left=((IN0+3)/W*100)+'%';b.style.top=((top(i)+5)/H*100)+'%';b.innerHTML=`<span class="lv">${f.lv}</span><span class="nm">${f.name}</span>`;b.setAttribute('aria-label',`${f.lv} ${f.name}`);b.onclick=()=>select(f.id,null);b.ondblclick=()=>openFloor(f.id);if(f.link)b.title='Double-click to open '+f.link.label.replace('Open ','');ov.appendChild(b);return b;});
for(const a of AGENTS){const el=document.createElement('div');el.className='tag';el.innerHTML=(a.id==='atlas'?'<div class="say" role="button" tabindex="0" hidden></div>':'')+`<span class="nm">${a.name}</span>`;ov.appendChild(el);a.el=el;}
const bubble=AGENTS.find(a=>a.id==='atlas').el.querySelector('.say');
bubble.addEventListener('click',e=>{if(e.target.closest('a'))return;select('travel',null);document.getElementById('detail').scrollIntoView({behavior:RM?'auto':'smooth',block:'nearest'});});
bubble.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();bubble.click();}});
function placeTags(){for(const a of AGENTS){a.el.style.left=(a.x/W*100)+'%';a.el.style.top=((feet(a.fi)-(a.lift||0)-16)/H*100)+'%';}}

/* ---------- directory + detail ---------- */
const dir=document.getElementById('dir'),detail=document.getElementById('detail');
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const health=a=>CEO_PAUSED?null:S.check?.agents?.[HID[a.id]||a.id];
const dotCls=a=>{const h=health(a);return h?'h-'+h.health:a.status;};
function renderDir(){
  dir.innerHTML='';
  FLOORS.forEach(f=>{const li=document.createElement('li');const ag=AGENTS.filter(a=>a.floor===f.id);const fh=CEO_PAUSED?null:S.check?.floors?.[f.id];
    const n=f.id==='lobby'?S.requests.filter(r=>r.status==='new').length:0;
    const sub=f.id==='travel'&&S.tv.best?`Best trip ${eur(S.tv.best.best.totalPP)} p.p. · ${S.tv.best.name}`:f.id==='lobby'&&n?`${n} request${n>1?'s':''} waiting for the CEO`:fh?`${ag.length} agent${ag.length>1?'s':''} · ${fh.note}`:f.sub;
    li.innerHTML=`<button type="button" data-f="${f.id}" aria-current="${f.id===selFloor}"><span class="knob">${f.knob}</span><span class="t"><b>${esc(f.name)}</b><span>${esc(sub)}</span></span><span class="dots">${ag.map(a=>`<span class="dot ${dotCls(a)}" title="${esc(a.name)}: ${esc(health(a)?.note||a.label)}"></span>`).join('')}</span></button>`;
    li.firstChild.onclick=()=>select(f.id,null);li.firstChild.ondblclick=()=>openFloor(f.id);if(f.link)li.firstChild.title='Double-click to open '+f.link.label.replace('Open ','');dir.appendChild(li);});
}
const fmt=iso=>{if(!iso)return'';const d=new Date(iso);if(isNaN(d))return'';const t=d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});return d.toDateString()===new Date().toDateString()?t:d.toLocaleDateString([], {weekday:'short',day:'numeric',month:'short'})+' '+t;};
function linkBtn(href,label,cls='mini',seen=''){return href?`<a class="${cls}" href="${esc(href)}"${href[0]==='#'?'':' target="_blank" rel="noopener"'}${seen?` data-seen="${esc(seen)}"`:''}>${esc(label||'Open')}${href[0]==='#'?' →':' ↗'}</a>`:'';}
/* live/flipdeck.seenAt is copied over by the hourly Flipdeck sweep when you've opened Flipdeck: anything found before then counts as checked */
function openAlerts(){if(CEO_PAUSED)return [];const seen=S.fdSeen||'';return (S.check?.alerts||[]).filter(x=>S.dismissed[x.key]!==x.sig&&!(x.newestAt&&seen&&x.newestAt<=seen));}
function openItems(){if(CEO_PAUSED)return [];const items=openAlerts().map(x=>({key:x.key,kind:x.kind,title:x.title,detail:x.detail,link:x.link,linkLabel:x.linkLabel}));
  const sg=S.suggestions.filter(x=>x.status==='pending').length;if(sg)items.push({kind:'check',title:`${sg} suggestion${sg>1?'s':''} waiting for your OK`,detail:'Approve or reject them on the CEO floor.'});
  const rp=S.requests.filter(x=>x.status==='answered'&&!x.seenAt).length;if(rp)items.push({kind:'check',title:`The CEO answered ${rp} request${rp>1?'s':''}`,detail:'Read it at the front desk.'});
  const age=S.check?(Date.now()-new Date(S.check.runAt))/36e5:0;
  if(age>7)items.unshift({kind:'broken',title:`The CEO hasn't checked in since ${fmt(S.check.runAt)}`,detail:'The CEO routine may have stopped. Ask Claude in a chat to look at it.'});
  return items;}
function renderBubble(){
  const it=openItems();if(!it.length){bubble.hidden=true;return;}
  const bad=it.some(x=>x.kind==='broken'),f=it[0];
  const html=`<b><i></i>${it.length===1?'1 thing to check':it.length+' things to check'}</b><span>${esc(f.title)}</span>${f.link?linkBtn(f.link,f.linkLabel,'',f.kind==='check'?f.key:''):''}`;
  if(bubble.dataset.h!==html){bubble.innerHTML=html;bubble.dataset.h=html;bubble.classList.toggle('bad',bad);}
  bubble.hidden=false;
}
function alertList(list){return `<ul class="items">${list.map(x=>`<li class="item"><span class="dot ${x.kind==='broken'?'h-down':'h-warn'}"></span><b>${esc(x.title)}</b>${x.detail?`<p>${esc(x.detail)}</p>`:''}<div class="acts">${linkBtn(x.link,x.linkLabel,'mini gold',x.kind==='check'?x.key:'')}<button class="mini" type="button" data-done="${esc(x.key)}">Done</button></div></li>`).join('')}</ul>`;}
const offline=()=>S.ready?'':`<p class="empty">${S.db===null?'Can\u2019t reach the CEO\u2019s notes from this view. Open the page on claude.ai while signed in.':'Loading the CEO\u2019s notes\u2026'}</p>`;
function ceoPanel(){
  if(CEO_PAUSED)return `<p class="health"><span class="dot standby"></span>Paused. The CEO routine is switched off, so nothing is checked, answered or reported. Your Flipdeck and Swing Desk agents still run and notify you themselves.</p><p class="lede2">Ask Claude in a chat to switch the CEO back on.</p>`;
  const c=S.check,al=openAlerts();
  let h=`<p class="health"><span class="dot ${!c?'standby':al.some(x=>x.kind==='broken')?'h-down':al.length?'h-warn':'h-ok'}"></span>${c?`${esc(c.summary)} · checked ${fmt(c.runAt)}`:'No check yet. The first one runs at the next check time.'}</p>`;
  h+=offline();
  h+=`<div class="sec"><h4>Needs you <em>${al.length||'nothing'}</em></h4>${al.length?alertList(al):'<p class="lede2">All quiet. The CEO only bothers you when something needs a look.</p>'}</div>`;
  const pend=S.suggestions.filter(x=>x.status==='pending'),done=S.suggestions.filter(x=>x.status!=='pending').slice(0,3);
  h+=`<div class="sec"><h4>Waiting for your OK <em>${pend.length||'none'}</em></h4>${pend.length?`<ul class="items">${pend.map(x=>`<li class="item"><span class="dot h-warn"></span><b>${esc(x.title)}</b>${x.why?`<p>${esc(x.why)}</p>`:''}${x.preview?`<pre>${esc(x.preview)}</pre>`:''}<div class="acts"><button class="mini gold" type="button" data-ok="${esc(x.id)}">Approve</button><button class="mini" type="button" data-no="${esc(x.id)}">Reject</button></div></li>`).join('')}</ul>`:'<p class="lede2">The CEO suggests changes to the agents once a week, and after your front-desk requests. Nothing changes until you approve it.</p>'}
    ${done.length?`<ul class="items" style="margin-top:8px">${done.map(x=>`<li class="item"><span class="dot ${x.status==='applied'?'h-ok':x.status==='failed'?'h-down':'h-off'}"></span><b>${esc(x.title)}</b><p>${{approved:'Approved · applied at the next check',rejected:'Rejected',applied:'Applied '+fmt(x.appliedAt),failed:'Could not apply: '+(x.result||'')}[x.status]||esc(x.status)}</p></li>`).join('')}</ul>`:''}</div>`;
  const r=S.report;
  h+=`<div class="sec report"><h4>Weekly report <em>${r?esc(r.week||fmt(r.createdAt)):'first one on Sunday'}</em></h4>${r?`${r.headline?`<p>${esc(r.headline)}</p>`:''}<ul>${(r.lines||[]).map(l=>`<li>${esc(l)}</li>`).join('')}</ul>`:'<p class="lede2">Deals found per agent, what you bought and sold, how the trading went, and which agents earn their keep.</p>'}</div>`;
  return h;
}
const eur=n=>n==null||isNaN(n)?'–':'€'+Math.round(n).toLocaleString('en-GB');
function travelPanel(){
  const c=S.tv.cfg;
  if(!S.db)return `<p class="empty">Open the page on claude.ai while signed in to see Atlas's trips.</p>`;
  if(!c)return `<p class="empty">Loading Atlas's notes…</p>`;
  const st=c.status==='running'?'h-warn':c.failStreak>1?'h-down':'h-ok';
  let h=`<p class="health"><span class="dot ${st}"></span>${c.status==='running'?'Searching right now…':'Last search '+(fmt(c.lastRunAt)||'not yet')}${c.runRequested&&c.status!=='running'?' · search queued':''}</p>`;
  const list=S.tv.trips.filter(x=>x.best).sort((a,b)=>a.best.totalPP-b.best.totalPP).slice(0,3);
  const max=c.budgetMaxPP??2500;
  h+=`<div class="sec"><h4>Best trips <em>all-in per person</em></h4>${list.length?`<ul class="items">${list.map(x=>`<li class="item"><span class="dot ${x.best.totalPP<=max?'h-ok':x.best.totalPP<=max*1.15?'h-warn':'h-down'}"></span><b>${esc(x.name)} · ${eur(x.best.totalPP)}</b><p>${esc(x.best.depart)} → ${esc(x.best.return)} · ${x.best.days} days · ${x.best.totalPP<=max?'within budget':eur(x.best.totalPP-max)+' over budget'}</p></li>`).join('')}</ul>`:'<p class="lede2">No priced trips yet. The first daily search fills this in.</p>'}</div>`;
  h+=`<div class="acts" style="display:flex;gap:8px;margin-top:12px"><button class="mini gold" type="button" data-tvrun ${c.runRequested||c.status==='running'?'disabled':''}>${c.runRequested?'Search queued':'Search now'}</button></div>`;
  return h;
}
async function tvRun(btn){if(!S.db)return;btn.disabled=true;try{await S.db.doc('travel_config/settings').update({runRequested:true,requestedAt:new Date().toISOString()});}catch(e){btn.disabled=false;btn.textContent='Try again';}}
function deskPanel(){
  if(CEO_PAUSED)return `<p class="empty">The front desk is closed while the CEO is paused. Ask Claude in a chat instead.</p>`;
  const reqs=S.requests;
  let h=`<div class="desk"><label for="reqText" class="kicker" style="display:block">Your request</label><textarea id="reqText" maxlength="600" placeholder="e.g. Find me a PS5 Slim under €250, or: why did Scent skip Vinted?"></textarea>
    <div class="row"><span id="reqMsg">The CEO answers at the next check.</span><button class="mini gold" type="button" id="reqSend" ${S.ready?'':'disabled'}>Leave with Noor</button></div></div>`;
  h+=offline();
  h+=`<div class="sec"><h4>Your requests <em>${reqs.length||'none yet'}</em></h4>${reqs.length?`<ul class="items">${reqs.map(x=>`<li class="item"><span class="dot ${x.status==='new'?'h-warn':'h-ok'}"></span><b>${esc(x.text)}</b><p>${x.status==='new'?'Waiting for the CEO · left '+fmt(x.createdAt):(x.routedTo?'Sent to '+esc(x.routedTo)+' · ':'')+'answered '+fmt(x.repliedAt)}</p>${x.reply?`<div class="reply"><small>CEO</small>${esc(x.reply)}</div>`:''}</li>`).join('')}</ul>`:'<p class="lede2">Nothing yet. Ask for a new search, a question about your agents, or an idea for a new floor.</p>'}</div>`;
  return h;
}
function renderDetail(){
  const f=FLOORS.find(x=>x.id===selFloor),ag=AGENTS.filter(a=>a.floor===f.id);
  const ta=document.getElementById('reqText'),draft=ta?ta.value:'',focus=ta&&document.activeElement===ta;
  const staff=ag.length?`<ul class="staff">${ag.map(a=>{const hh=health(a);return `<li data-a="${a.id}" class="${a.id===selAgent?'sel':''}"><b>${esc(a.name)}</b><span class="chip"><span class="dot ${dotCls(a)}"></span>${esc(hh?hh.note:a.label)}</span><span class="role">${esc(a.role)}</span></li>`;}).join('')}</ul>`
    :`<p class="empty">No agents work here.</p>`;
  const facts=f.facts.length?`<dl class="facts">${f.facts.map(([k,v])=>`<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`:'';
  const floorAlerts=openAlerts().filter(x=>x.floor===f.id||(x.floor==='flip'&&(f.id==='tech'||f.id==='collect')));
  const extra=f.id==='travel'?travelPanel():f.id==='lobby'?deskPanel():(floorAlerts.length?`<div class="sec"><h4>CEO says</h4>${alertList(floorAlerts)}</div>`:'');
  detail.innerHTML=`<p class="kicker">${f.lv==='G'?'Ground floor':'Floor '+f.knob}</p><h3>${esc(f.name)}</h3><p>${esc(f.text)}</p>${staff}${extra}${facts}${f.link?`<a class="go" href="${f.link.href}"${f.link.href[0]==='#'?'':' target="_blank" rel="noopener"'}><span>${f.link.label}<small>${f.link.hint}</small></span><span class="arw" aria-hidden="true">${f.link.href[0]==='#'?'→':'↗'}</span></a>`:''}`;
  detail.querySelectorAll('[data-a]').forEach(li=>li.onclick=()=>select(f.id,li.dataset.a));
  const tvb=detail.querySelector('[data-tvrun]');if(tvb)tvb.onclick=()=>tvRun(tvb);
  detail.querySelectorAll('[data-done]').forEach(b=>b.onclick=()=>dismiss(b.dataset.done));
  detail.querySelectorAll('[data-ok]').forEach(b=>b.onclick=()=>decide(b.dataset.ok,'approved',b));
  detail.querySelectorAll('[data-no]').forEach(b=>b.onclick=()=>decide(b.dataset.no,'rejected',b));
  const nta=document.getElementById('reqText');if(nta){nta.value=draft;if(focus)nta.focus();document.getElementById('reqSend').onclick=sendRequest;}
  if(f.id==='lobby')markSeen();
  plates.forEach((p,i)=>p.classList.toggle('sel',FLOORS[i].id===selFloor));
  AGENTS.forEach(a=>a.el.classList.toggle('sel',a.id===selAgent));
  renderDir();
}
function select(f,a){selFloor=f;selAgent=a;renderDetail();}
/* opening a 'check' alert's link counts as checking it: the CEO stops showing it until something new comes in */
document.addEventListener('click',e=>{const a=e.target.closest&&e.target.closest('a[data-seen]');if(a)setTimeout(()=>dismiss(a.dataset.seen),0);},true);
function openFloor(id){const f=FLOORS.find(x=>x.id===id);if(!f||!f.link)return;if(f.link.href[0]==='#'){location.hash=f.link.href;return;}const a=document.createElement('a');a.href=f.link.href;a.target='_blank';a.rel='noopener';document.body.appendChild(a);a.click();a.remove();}

/* ---------- CEO database ---------- */
const S={db:undefined,ready:false,check:null,dismissed:{},suggestions:[],requests:[],report:null,fdSeen:'',tv:{cfg:null,trips:[],best:null}};
function refresh(){renderDetail();renderBubble();}
async function dismiss(key){const x=(S.check?.alerts||[]).find(a=>a.key===key);if(!x||!S.db)return;S.dismissed[key]=x.sig;refresh();
  try{await S.db.doc('dismissed/'+key).set({sig:x.sig,at:new Date().toISOString()});}catch(e){delete S.dismissed[key];refresh();}}
async function decide(id,status,btn){if(!S.db)return;btn.disabled=true;
  try{await S.db.doc('suggestions/'+id).update({status,decidedAt:new Date().toISOString()});}catch(e){btn.disabled=false;btn.textContent='Try again';}}
async function sendRequest(){const ta=document.getElementById('reqText'),msg=document.getElementById('reqMsg'),txt=ta.value.trim();
  if(!txt){msg.textContent='Type a request first.';ta.focus();return;}if(!S.db)return;
  const b=document.getElementById('reqSend');b.disabled=true;
  try{await S.db.collection('requests').add({text:txt.slice(0,600),status:'new',createdAt:new Date().toISOString()});ta.value='';msg.textContent='Noor passed it on. The CEO answers at the next check.';}
  catch(e){msg.textContent='Couldn\u2019t save that. Try again in a moment.';}
  b.disabled=false;}
let seenBusy=false;
async function markSeen(){if(seenBusy||!S.db)return;const todo=S.requests.filter(r=>r.status==='answered'&&!r.seenAt);if(!todo.length)return;seenBusy=true;
  try{for(const r of todo)await S.db.doc('requests/'+r.id).update({seenAt:new Date().toISOString()});}catch(e){}seenBusy=false;}
(async()=>{
  let db=null;try{db=window.claude?.use?await window.claude.use('db'):null;}catch(e){db=null;}
  S.db=db;if(!db){refresh();return;}
  const rows=q=>q.docs.map(d=>({id:d.id,...d.data()}));
  let n=0;const done=()=>{if(++n>=4&&!S.ready){S.ready=true;}refresh();};
  const err=()=>{done();};
  db.collection('checks').orderBy('runAt','desc').limit(1).onSnapshot(q=>{S.check=rows(q)[0]||null;done();},err);
  db.collection('dismissed').onSnapshot(q=>{S.dismissed=Object.fromEntries(q.docs.map(d=>[d.id,d.data()?.sig]));done();},err);
  db.collection('suggestions').orderBy('createdAt','desc').limit(30).onSnapshot(q=>{S.suggestions=rows(q);done();},err);
  db.collection('requests').orderBy('createdAt','desc').limit(20).onSnapshot(q=>{S.requests=rows(q);done();},err);
  db.collection('reports').orderBy('createdAt','desc').limit(1).onSnapshot(q=>{S.report=rows(q)[0]||null;refresh();},()=>{});
  db.doc('travel_config/settings').onSnapshot(d=>{S.tv.cfg=d.exists?d.data():null;refresh();},()=>{});
  db.collection('travel_trips').onSnapshot(q=>{S.tv.trips=rows(q);S.tv.best=S.tv.trips.filter(x=>x.best).sort((a,b)=>a.best.totalPP-b.best.totalPP)[0]||null;refresh();},()=>{});
  db.doc('live/flipdeck').onSnapshot(d=>{S.fdSeen=(d.exists&&d.data()?.seenAt)||'';refresh();},()=>{});
})();

/* ---------- canvas input ---------- */
function hit(e){const r=cv.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*W,y=(e.clientY-r.top)/r.height*H;
  for(const a of AGENTS){const fy=feet(a.fi)-(a.lift||0);if(Math.abs(x-a.x)<=5&&y>=fy-16&&y<=fy+2)return{a};}
  if(x>=IN0&&x<=IN1)for(let i=0;i<FLOORS.length;i++)if(y>=top(i)+3&&y<top(i)+FH)return{f:FLOORS[i].id};return null;}
cv.addEventListener('click',e=>{const h=hit(e);if(!h)return;if(h.a)select(h.a.floor,h.a.id);else select(h.f,null);});
cv.addEventListener('dblclick',e=>{const h=hit(e);if(h)openFloor(h.a?h.a.floor:h.f);});
cv.addEventListener('mousemove',e=>cv.classList.toggle('hot',!!hit(e)));

const tower=document.getElementById('tower'),tagsBtn=document.getElementById('tagsBtn'),pauseBtn=document.getElementById('pauseBtn');
tagsBtn.onclick=()=>{const on=tagsBtn.getAttribute('aria-pressed')!=='true';tagsBtn.setAttribute('aria-pressed',on);tower.classList.toggle('tags-off',!on);};
let paused=RM;pauseBtn.setAttribute('aria-pressed',paused);pauseBtn.textContent=paused?'Play':'Pause';
pauseBtn.onclick=()=>{paused=!paused;pauseBtn.setAttribute('aria-pressed',paused);pauseBtn.textContent=paused?'Play':'Pause';};

/* ---------- clock ---------- */
const clk=document.getElementById('clk'),shift=document.getElementById('shift');
function clock(){const n=new Date();clk.textContent=n.toTimeString().slice(0,5);const k=skyFor(n.getHours());shift.textContent={night:'night shift',dawn:'early shift',day:'day shift',dusk:'evening shift'}[k.k];if(k.k!==sky.k){sky=k;buildStatic();}}

/* ---------- loop ---------- */
buildStatic();clock();setInterval(clock,15000);refresh();
let last=performance.now();
function frame(now){
  const dt=Math.min(.1,(now-last)/1000);last=now;const t=now/1000;
  if(!paused){
    for(const a of AGENTS)upd(a,dt);
    monT+=dt;if(monT>1.4){monT=0;const m=mons[Math.floor(Math.random()*4)];const o=m[m.length-1].c,c=Math.min(.95,Math.max(.05,o+rand(-.2,.21)));m.shift();m.push({o,c,h:Math.max(o,c)+rand(0,.08),l:Math.min(o,c)-rand(0,.08)});}
    wallT+=dt;if(wallT>.35){wallT=0;wall.shift();wall.push(Math.min(.95,Math.max(.05,wall[wall.length-1]+rand(-.07,.075))));}
    if(lift.wait>0)lift.wait-=dt;else{const ty=feet(lift.target)-22,d=ty-lift.y;if(Math.abs(d)<1){lift.y=ty;lift.wait=rand(2.5,6);let n;do{n=Math.floor(Math.random()*5)}while(n===lift.target);lift.target=n;}else lift.y+=Math.sign(d)*Math.min(Math.abs(d),26*dt);}
  }
  g.drawImage(stc,0,0);
  drawLive(paused?0:t);
  FLOORS.forEach((f,i)=>{if(f.id!==selFloor){g.fillStyle='rgba(4,6,12,.32)';g.fillRect(IN0,top(i)+3,IN1-IN0,FH-3);}});
  const si=FI[selFloor],T=top(si);R(g,'#d6a957',IN0,T+3,IN1-IN0,1);R(g,'#d6a957',IN0,T+FH-1,IN1-IN0,1);R(g,'#d6a957',IN0,T+3,1,FH-3);R(g,'#d6a957',IN1-1,T+3,1,FH-3);
  for(const a of AGENTS)drawAgent(a);
  {const F=feet(4);g.drawImage(stc,180,F-13,64,13,180,F-13,64,13);g.drawImage(stc,192,F-19,10,7,192,F-19,10,7);}
  placeTags();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
})();
