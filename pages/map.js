const svg = document.querySelector('#map-svg');
const viewport = document.querySelector('#viewport');
const ns = 'http://www.w3.org/2000/svg';
const point = ([lon, lat]) => [400 + (lon - 21) * 103, 360 - (lat - 44) * 144];
const element = (name, attrs = {}) => { const el = document.createElementNS(ns, name); for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value); return el; };
const cities = [
  ['Beograd','Београд',20.46,44.82], ['Novi Sad','Нови Сад',19.84,45.26], ['Subotica','Суботица',19.67,46.10],
  ['Niš','Ниш',21.90,43.32], ['Kragujevac','Крагујевац',20.92,44.01], ['Užice','Ужице',19.84,43.86],
  ['Novi Pazar','Нови Пазар',20.52,43.14], ['Priština','Приштина',21.16,42.66], ['Prizren','Призрен',20.74,42.21]
];
let cyrillic = false;
const texts = {
 edition:['DIGITALNI ATLAS · IZDANJE 01','ДИГИТАЛНИ АТЛАС · ИЗДАЊЕ 01'], eyebrow:['PROJEKAT U NASTAJANJU ✳ 2026','ПРОЈЕКАТ У НАСТАЈАЊУ ✳ 2026'],
 title:['Srbija,<br><em>iz drugog ugla.</em>','Србија,<br><em>из другог угла.</em>'], intro:['Zemlja kao strateška mapa. Prvi pogled na prostor koji će postati SerbiaCiv.','Земља као стратешка мапа. Први поглед на простор који ће постати SerbiaCiv.'], explore:['ISTRAŽI MAPU <span>↘</span>','ИСТРАЖИ МАПУ <span>↘</span>'],
 mapTitle:['Teritorija','Територија'], mapNote:['KARTOGRAFSKI PREGLED<br>GRANICE · GRADOVI','КАРТОГРАФСКИ ПРЕГЛЕД<br>ГРАНИЦЕ · ГРАДОВИ'], caption:['Pregledna mapa<br><strong>Podaci o reljefu i statistici slede.</strong>','Прегледна мапа<br><strong>Подаци о рељефу и статистици следе.</strong>'],
 legend:['● ODABRANI GRADOVI &nbsp;&nbsp; ⬡ ILUSTRATIVNA MREŽA','● ОДАБРАНИ ГРАДОВИ &nbsp;&nbsp; ⬡ ИЛУСТРАТИВНА МРЕЖА'], aboutTitle:['Mapa je tek<br><em>početak.</em>','Мапа је тек<br><em>почетак.</em>'],
 about:['SerbiaCiv je projekat otvorenog koda koji pretvara javne podatke u atlas inspirisan strateškim igrama. Ovaj pregled prikazuje obris i izabrane gradove; heksagonalni teren, statistika i ostali slojevi su u izradi.','SerbiaCiv је пројекат отвореног кода који претвара јавне податке у атлас инспирисан стратешким играма. Овај преглед приказује обрис и изабране градове; хексагонални терен, статистика и остали слојеви су у изради.'],
 source:['POGLEDAJ KOD PROJEKTA ↗','ПОГЛЕДАЈ КОД ПРОЈЕКТА ↗'], credit:['OBRIS: <a href="https://www.naturalearthdata.com/">NATURAL EARTH</a> · JAVNO VLASNIŠTVO','ОБРИС: <a href="https://www.naturalearthdata.com/">NATURAL EARTH</a> · ЈАВНО ВЛАСНИШТВО'], based:['NASTALO NA OSNOVU <a href="https://karpathy.ai/usaciv/">USACIV</a>','НАСТАЛО НА ОСНОВУ <a href="https://karpathy.ai/usaciv/">USACIV</a>'], error:['Mapa nije učitana. Osvežite stranicu i pokušajte ponovo.','Мапа није учитана. Освежите страницу и покушајте поново.']
};
function translate(){document.documentElement.lang=cyrillic?'sr-Cyrl':'sr-Latn';document.querySelectorAll('[data-i]').forEach(el=>el.innerHTML=texts[el.dataset.i][Number(cyrillic)]);document.querySelector('#script').textContent=cyrillic?'LAT':'ЋИР';document.querySelectorAll('[data-city]').forEach(el=>el.textContent=cities[Number(el.dataset.city)][Number(cyrillic)]);}
document.querySelector('#script').addEventListener('click',()=>{cyrillic=!cyrillic;translate();});
let scale=1; function zoom(){viewport.setAttribute('transform',`translate(${400*(1-scale)} ${360*(1-scale)}) scale(${scale})`)}
document.querySelector('#zoom-in').addEventListener('click',()=>{scale=Math.min(2,scale+.25);zoom()});
document.querySelector('#zoom-out').addEventListener('click',()=>{scale=Math.max(1,scale-.25);zoom()});
document.querySelector('#reset').addEventListener('click',()=>{scale=1;zoom()});
try {
 const response=await fetch('outline.json'); if(!response.ok) throw new Error('outline unavailable');
 const shapes=await response.json();
 const path=shapes.flatMap(shape=>shape.type==='Polygon'?[shape.coordinates]:shape.coordinates).flatMap(polygon=>polygon.map(ring=>ring.map((p,i)=>`${i?'L':'M'}${point(p).map(n=>n.toFixed(1)).join(' ')}`).join('')+'Z')).join('');
 const group=document.querySelector('#shape'); group.append(element('path',{d:path,fill:'#7e9a78','fill-rule':'evenodd'}),element('path',{d:path,fill:'url(#hex)','fill-rule':'evenodd'}));
 cities.forEach(([lat,cy,lon,y],i)=>{const [x,py]=point([lon,y]); const g=element('g');g.append(element('circle',{cx:x,cy:py,r:i===0?5:3.5,fill:'#a84f31',stroke:'#efe9d6','stroke-width':'2'}));const label=element('text',{x:x+9,y:py-7,fill:'#263d30','font-family':'DM Sans, sans-serif','font-size':'12','font-weight':'700','paint-order':'stroke',stroke:'#d6ddc9','stroke-width':'3','stroke-linejoin':'round','data-city':i});label.textContent=lat;g.append(label);document.querySelector('#cities').append(g)});
} catch(err) {document.querySelector('#error').hidden=false;console.error(err)}
