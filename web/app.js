const translations={
  en:{brand:'Frost Risk Maps',nav_maps:'Maps',nav_methods:'Methods',theme:'Theme',domain:'Southern Brazil · five-state domain',hero_title:'Frost Risk Maps',hero_text:'Explore frost occurrence, HAND and terrain elevation across Paraná, Santa Catarina, Rio Grande do Sul, São Paulo and Mato Grosso do Sul.',states:'states',terrain_grid:'terrain grid',climate_period:'climate period',interactive_kicker:'Interactive map',interactive_title:'Explore the mapped layers',interactive_text:'Search for a city, switch layers and inspect local patterns. Downloads retain the analytical GeoTIFF values.',search_label:'Search for a city or region',search_placeholder:'Search a city or region…',search_button:'Find',place_not_found:'Location not found. Try a city and state.',place_found:'Showing',preview_badge:'Map preview',choose_layer:'Choose a layer',opacity:'Opacity',selected_layer:'Selected layer',display_range:'Display range',native_grid:'Native grid',coverage:'Coverage',download_geotiff:'Download GeoTIFF',about_kicker:'About',about_title:'Research maps for regional frost assessment',about_text:'The portal presents model outputs and terrain context. It is a research product, not an operational weather forecast.',read_methods:'Read the methods',valid_cells:'valid cells'},
  pt:{brand:'Mapas de Risco de Geada',nav_maps:'Mapas',nav_methods:'Métodos',theme:'Tema',domain:'Sul do Brasil · domínio de cinco estados',hero_title:'Mapas de Risco de Geada',hero_text:'Explore a ocorrência de geada, o HAND e a elevação do terreno no Paraná, Santa Catarina, Rio Grande do Sul, São Paulo e Mato Grosso do Sul.',states:'estados',terrain_grid:'grade do terreno',climate_period:'período climático',interactive_kicker:'Mapa interativo',interactive_title:'Explore as camadas mapeadas',interactive_text:'Busque uma cidade, alterne as camadas e examine padrões locais. Os downloads preservam os valores analíticos dos GeoTIFFs.',search_label:'Buscar cidade ou região',search_placeholder:'Buscar cidade ou região…',search_button:'Buscar',place_not_found:'Local não encontrado. Tente informar a cidade e o estado.',place_found:'Exibindo',preview_badge:'Prévia do mapa',choose_layer:'Escolha uma camada',opacity:'Opacidade',selected_layer:'Camada selecionada',display_range:'Intervalo visual',native_grid:'Grade nativa',coverage:'Cobertura',download_geotiff:'Baixar GeoTIFF',about_kicker:'Sobre',about_title:'Mapas científicos para avaliação regional de geada',about_text:'O portal apresenta resultados dos modelos e o contexto do terreno. É um produto de pesquisa, não uma previsão meteorológica operacional.',read_methods:'Ler os métodos',valid_cells:'células válidas'}
};

Object.assign(translations.en,{analysis_tools:'Inspect and analyze',analysis_hint:'Click the map to inspect a value, or draw an area to summarize it.',draw_rectangle:'Rectangle',draw_polygon:'Polygon',clear_selection:'Clear',no_selection:'No area selected.',selected_area:'Selected area',sampled_cells:'Sampled cells',minimum:'Minimum',mean:'Mean',median:'Median',maximum:'Maximum',analysis_note:'Statistics use a numerical web grid; download the GeoTIFF for native-resolution analysis.',loading_values:'Loading numerical values…',no_valid_values:'No valid values in this selection.',point_value:'Map value',coordinates:'Coordinates',group_complete:'Complete period',group_enso:'ENSO phases',group_terrain:'Terrain'});
Object.assign(translations.pt,{analysis_tools:'Inspecionar e analisar',analysis_hint:'Clique no mapa para consultar um valor ou desenhe uma área para resumi-la.',draw_rectangle:'Retângulo',draw_polygon:'Polígono',clear_selection:'Limpar',no_selection:'Nenhuma área selecionada.',selected_area:'Área selecionada',sampled_cells:'Células amostradas',minimum:'Mínimo',mean:'Média',median:'Mediana',maximum:'Máximo',analysis_note:'As estatísticas usam uma grade numérica web; baixe o GeoTIFF para análises na resolução nativa.',loading_values:'Carregando valores numéricos…',no_valid_values:'Não há valores válidos nesta seleção.',point_value:'Valor do mapa',coordinates:'Coordenadas',group_complete:'Período completo',group_enso:'Fases do ENSO',group_terrain:'Terreno'});

Object.assign(translations.en,{
  brand:'Environmental Maps',nav_collections:'Collections',nav_maps:'Map explorer',nav_methods:'Methods & data',theme:'Theme',
  domain:'Camcore geospatial portal',hero_title:'Environmental maps for science and informed decisions.',hero_text:'Explore scientific map collections connecting climate, terrain and environmental decision support.',
  collections_count:'map collections',languages:'languages',research_data:'research data',collections_kicker:'Map collections',collections_title:'Choose a research theme',
  collections_text:'Each collection has its own scientific scope, map catalogue and visual identity. New collections can be added without changing the existing portal.',
  available_now:'Available now',preview_available:'Preview available',reserved:'Reserved',frost_type:'Climate hazard',decision_support:'Decision support',environmental_context:'Environmental context',
  frost_collection:'Frost Climatology',species_collection:'Species Suitability',bioclimate_collection:'Bioclimatic Variables',
  frost_collection_text:'Occurrence probability, expected frost days, seasonal minimum temperature and terrain context.',species_collection_text:'Analyses based on the natural ranges of the species.',bioclimate_collection_text:'Global BIO1–BIO19 temperature and precipitation summaries for 1981–2024.',empty_collection:'Collection space reserved for future datasets.',open_collection:'Open collection',
  interactive_title:'Explore the frost-climatology layers',about_kicker:'Data access',about_title:'Selected analytical maps are available for download.',
  about_text:'The complete 2000–2026 frost-climatology collection and its analytical GeoTIFFs are archived on Zenodo under DOI 10.5281/zenodo.21918677.',
  read_methods:'Methods & data',open_dataset:'Open Zenodo dataset',footer_brand:'Camcore Environmental Map Collections',footer_text:'Research maps and decision support'
});
Object.assign(translations.pt,{
  brand:'Mapas Ambientais',nav_collections:'Coleções',nav_maps:'Explorador de mapas',nav_methods:'Métodos e dados',theme:'Tema',
  domain:'Portal geoespacial Camcore',hero_title:'Mapas ambientais para ciência e decisões bem fundamentadas.',hero_text:'Explore coleções científicas que conectam clima, terreno e apoio à decisão ambiental.',
  collections_count:'coleções de mapas',languages:'idiomas',research_data:'dados científicos',collections_kicker:'Coleções de mapas',collections_title:'Escolha um tema de pesquisa',
  collections_text:'Cada coleção possui escopo científico, catálogo de mapas e identidade visual próprios. Novas coleções podem ser adicionadas sem alterar o restante do portal.',
  available_now:'Disponível agora',preview_available:'Prévia disponível',reserved:'Reservada',frost_type:'Risco climático',decision_support:'Apoio à decisão',environmental_context:'Contexto ambiental',
  frost_collection:'Climatologia de Geadas',species_collection:'Adequabilidade de Espécies',bioclimate_collection:'Variáveis Bioclimáticas',
  frost_collection_text:'Probabilidade de ocorrência, dias esperados de geada, temperatura mínima sazonal e contexto do terreno.',species_collection_text:'Análises baseadas nas distribuições naturais das espécies.',bioclimate_collection_text:'Sínteses globais BIO1–BIO19 de temperatura e precipitação para 1981–2024.',empty_collection:'Espaço reservado para conjuntos de dados futuros.',open_collection:'Abrir coleção',
  interactive_title:'Explore as camadas de climatologia de geadas',about_kicker:'Acesso aos dados',about_title:'Mapas analíticos selecionados estão disponíveis para download.',
  about_text:'A coleção completa de climatologia de geadas de 2000–2026 e seus GeoTIFFs analíticos estão arquivados no Zenodo sob o DOI 10.5281/zenodo.21918677.',
  read_methods:'Métodos e dados',open_dataset:'Abrir conjunto de dados no Zenodo',footer_brand:'Coleções de Mapas Ambientais Camcore',footer_text:'Mapas científicos e apoio à decisão'
});

Object.assign(translations.en,{basemap_map:'Map',basemap_satellite:'Satellite',fullscreen_map:'Full screen map',exit_fullscreen:'Exit full screen'});
Object.assign(translations.pt,{basemap_map:'Mapa',basemap_satellite:'Satélite',fullscreen_map:'Mapa em tela cheia',exit_fullscreen:'Sair da tela cheia'});

Object.assign(translations.en,{
  zenodo_doi:'Download dataset · DOI 10.5281/zenodo.21918677',
  species_zenodo_doi:'Download dataset · DOI 10.5281/zenodo.21939047',
  download_zenodo_file:'Download GeoTIFF from Zenodo',
  open_zenodo_repository:'Open Zenodo repository',
  open_anadem_source:'Open ANADEM source',
  zenodo_file_note:'Archived analytical GeoTIFF (2000–2026).',
  zenodo_repository_note:'This displayed scenario is not included as a separate file in the current Zenodo record.',
  anadem_source_note:'ANADEM is distributed by its original data provider.'
});
Object.assign(translations.pt,{
  zenodo_doi:'Baixar conjunto de dados · DOI 10.5281/zenodo.21918677',
  species_zenodo_doi:'Baixar conjunto de dados · DOI 10.5281/zenodo.21939047',
  download_zenodo_file:'Baixar GeoTIFF pelo Zenodo',
  open_zenodo_repository:'Abrir repositório no Zenodo',
  open_anadem_source:'Abrir fonte do ANADEM',
  zenodo_file_note:'GeoTIFF analítico arquivado (2000–2026).',
  zenodo_repository_note:'Este cenário exibido não está incluído como arquivo separado no registro atual do Zenodo.',
  anadem_source_note:'O ANADEM é distribuído por seu provedor de dados original.'
});

Object.assign(translations.en,{heat_type:'Thermal climatology',heat_collection:'Heat Maps',heat_collection_text:'Monthly P95 maximum-temperature maps for 2000–2025.',provenance_type:'Genetic resources',provenance_collection:'Camcore Tested Provenances',provenance_collection_text:'Species catalogues and mapped origins represented in Camcore provenance testing.'});
Object.assign(translations.pt,{heat_type:'Climatologia térmica',heat_collection:'Mapas de Calor',heat_collection_text:'Mapas mensais do percentil 95 da temperatura máxima para 2000–2025.',provenance_type:'Recursos genéticos',provenance_collection:'Procedências Testadas pela Camcore',provenance_collection_text:'Catálogos de espécies e origens geográficas representadas nos testes de procedências da Camcore.'});

const layerText={
  en:{frost_probability:['Frost-occurrence probability','Reduced block-balanced Random Forest · 2000–2025','Complete five-state analytical surface'],expected_frost_days:['Expected frost days per season','Reduced block-balanced Random Forest · 2000–2025','Complete five-state analytical surface'],seasonal_tmin:['Seasonal minimum temperature','Reduced block-balanced Random Forest · 2000–2025','Complete five-state analytical surface'],hand:['Height above nearest drainage','HAND derived from ANADEM · 2-km flow-path search','Derived terrain layer'],anadem:['Terrain elevation','ANADEM v1 digital terrain model · native ~30 m','Third-party source layer; cite Laipelt et al. (2024)']},
  pt:{frost_probability:['Probabilidade de ocorrência de geada','Random Forest reduzido e balanceado por blocos · 2000–2025','Superfície analítica completa para os cinco estados'],expected_frost_days:['Dias esperados de geada por temporada','Random Forest reduzido e balanceado por blocos · 2000–2025','Superfície analítica completa para os cinco estados'],seasonal_tmin:['Temperatura mínima sazonal','Random Forest reduzido e balanceado por blocos · 2000–2025','Superfície analítica completa para os cinco estados'],hand:['Altura acima da drenagem mais próxima','HAND derivado do ANADEM · busca de fluxo de 2 km','Camada derivada do terreno'],anadem:['Elevação do terreno','Modelo digital de terreno ANADEM v1 · ~30 m nativos','Camada de terceiros; cite Laipelt et al. (2024)']}
};

const places=[
  ['Curitiba, PR',-25.4284,-49.2733],['Guarapuava, PR',-25.3905,-51.4628],['Ponta Grossa, PR',-25.0945,-50.1633],['São Mateus do Sul, PR',-25.8677,-50.3840],['União da Vitória, PR',-26.2273,-51.0873],['Irati, PR',-25.4697,-50.6493],
  ['Florianópolis, SC',-27.5949,-48.5482],['Lages, SC',-27.8150,-50.3259],['Caçador, SC',-26.7757,-51.0120],['Canoinhas, SC',-26.1772,-50.3949],['Mafra, SC',-26.1159,-49.8086],['Timbó Grande, SC',-26.6127,-50.6738],['Blumenau, SC',-26.9155,-49.0709],
  ['Porto Alegre, RS',-30.0346,-51.2177],['Santa Maria, RS',-29.6868,-53.8149],['Vacaria, RS',-28.5071,-50.9412],['São José dos Ausentes, RS',-28.7476,-50.0651],
  ['São Paulo, SP',-23.5505,-46.6333],['Capão Bonito, SP',-24.0063,-48.3496],['Itapeva, SP',-23.9820,-48.8759],
  ['Campo Grande, MS',-20.4697,-54.6201],['Dourados, MS',-22.2218,-54.8064]
];

const palettes={RdYlBu:'linear-gradient(90deg,#a50026,#f46d43,#ffffbf,#74add1,#313695)',RdYlBu_r:'linear-gradient(90deg,#313695,#74add1,#ffffbf,#f46d43,#a50026)',viridis:'linear-gradient(90deg,#440154,#3b528b,#21918c,#5ec962,#fde725)',gist_earth:'linear-gradient(90deg,#17336b,#478d82,#a9b26f,#c49a6c,#f5f2ed)'};
const ZENODO_RECORD='https://doi.org/10.5281/zenodo.21918677';
const ZENODO_FILES={
  frost_probability:'https://zenodo.org/records/21918677/files/FROST_PROBABILITY_MEAN_2000_2026.tif',
  expected_frost_days:'https://zenodo.org/records/21918677/files/FROST_DAYS_MEAN_2000_2026.tif',
  seasonal_tmin:'https://zenodo.org/records/21918677/files/TMIN_MEAN_2000_2026.tif',
  seasonal_tmin_p25:'https://zenodo.org/records/21918677/files/TMIN_P25_2000_2026.tif',
  hand:'https://zenodo.org/records/21918677/files/HAND_2000M.tif'
};
function downloadContract(layer){
  if(ZENODO_FILES[layer.id])return{href:ZENODO_FILES[layer.id],label:'download_zenodo_file',note:'zenodo_file_note',kind:'file'};
  if(layer.id==='anadem')return{href:layer.download,label:'open_anadem_source',note:'anadem_source_note',kind:'source'};
  return{href:ZENODO_RECORD,label:'open_zenodo_repository',note:'zenodo_repository_note',kind:'repository'}
}
const state={catalog:window.FROST_LAYERS||[],overlay:null,marker:null,active:null,opacity:.88,lang:localStorage.getItem('frost-lang')||'en',basemapType:localStorage.getItem('frost-basemap')||'map',analysisCache:{},analysisPromises:{},selectionLayer:null,selectionSamples:[],selectionStats:null,drawing:false};
const initialTheme=localStorage.getItem('frost-theme')||'dark';
document.documentElement.dataset.theme=initialTheme;

const map=L.map('map',{zoomControl:false,preferCanvas:true,minZoom:4,maxZoom:11});
L.control.zoom({position:'topright'}).addTo(map);
L.control.scale({imperial:false,position:'bottomleft'}).addTo(map);
map.createPane('labelsPane');map.getPane('labelsPane').style.zIndex=650;map.getPane('labelsPane').style.pointerEvents='none';
const cartographicBase=L.tileLayer('',{attribution:'&copy; OpenStreetMap &copy; CARTO',maxZoom:18});
const cartographicLabels=L.tileLayer('',{pane:'labelsPane',attribution:'&copy; OpenStreetMap &copy; CARTO',maxZoom:18});
const satelliteBase=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles &copy; Esri',maxZoom:18});
const satelliteLabels=L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',{pane:'labelsPane',attribution:'Labels &copy; Esri',maxZoom:18});
function updateBasemap(){
  [cartographicBase,cartographicLabels,satelliteBase,satelliteLabels].forEach(layer=>{if(map.hasLayer(layer))map.removeLayer(layer)});
  if(state.basemapType==='satellite'){satelliteBase.addTo(map);satelliteLabels.addTo(map)}
  else{const dark=document.documentElement.dataset.theme==='dark';cartographicBase.setUrl(`https://{s}.basemaps.cartocdn.com/${dark?'dark_nolabels':'light_nolabels'}/{z}/{x}/{y}{r}.png`);cartographicLabels.setUrl(`https://{s}.basemaps.cartocdn.com/${dark?'dark_only_labels':'light_only_labels'}/{z}/{x}/{y}{r}.png`);cartographicBase.addTo(map);cartographicLabels.addTo(map)}
  document.querySelectorAll('.basemap-option').forEach(button=>button.classList.toggle('active',button.dataset.basemap===state.basemapType));
}
const MapTools=L.Control.extend({options:{position:'topright'},onAdd(){const container=L.DomUtil.create('div','leaflet-bar map-tools-control');container.innerHTML='<button class="basemap-option" data-basemap="map" type="button">Map</button><button class="basemap-option" data-basemap="satellite" type="button">Satellite</button><button class="fullscreen-map" type="button" aria-pressed="false" aria-label="Full screen map" title="Full screen map">&#x26F6;</button>';L.DomEvent.disableClickPropagation(container);L.DomEvent.disableScrollPropagation(container);container.querySelectorAll('.basemap-option').forEach(button=>button.addEventListener('click',()=>{state.basemapType=button.dataset.basemap;localStorage.setItem('frost-basemap',state.basemapType);updateBasemap()}));container.querySelector('.fullscreen-map').addEventListener('click',toggleMapFullscreen);return container}});
new MapTools().addTo(map);
function toggleMapFullscreen(){const stage=document.querySelector('.map-stage'),active=stage.classList.toggle('map-fullscreen');document.body.classList.toggle('map-fullscreen-open',active);const button=document.querySelector('.fullscreen-map');button.setAttribute('aria-pressed',String(active));button.textContent=active?'×':'⛶';updateMapToolLanguage();setTimeout(()=>map.invalidateSize(),80)}
function updateMapToolLanguage(){const t=translations[state.lang],mapButton=document.querySelector('[data-basemap="map"]'),satelliteButton=document.querySelector('[data-basemap="satellite"]'),fullscreenButton=document.querySelector('.fullscreen-map'),active=document.querySelector('.map-stage')?.classList.contains('map-fullscreen');if(mapButton)mapButton.textContent=t.basemap_map||'Map';if(satelliteButton)satelliteButton.textContent=t.basemap_satellite||'Satellite';if(fullscreenButton){const label=active?(t.exit_fullscreen||'Exit full screen'):(t.fullscreen_map||'Full screen map');fullscreenButton.setAttribute('aria-label',label);fullscreenButton.title=label}}
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.querySelector('.map-stage')?.classList.contains('map-fullscreen'))toggleMapFullscreen()});
updateBasemap();

function fmt(value){return Math.abs(value)>=100?Math.round(value).toLocaleString():Number(value).toFixed(2)}
function localizedLayer(layer){
  const legacy=layerText[state.lang][layer.id];
  if(state.lang==='pt'&&(layer.titlePt||layer.subtitlePt||layer.statusPt))return[layer.titlePt||layer.title,layer.subtitlePt||layer.subtitle,layer.statusPt||layer.status];
  return legacy||[layer.title,layer.subtitle,layer.status]
}
function renderLanguage(){
  document.documentElement.lang=state.lang;
  document.querySelectorAll('[data-i18n]').forEach(el=>{const value=translations[state.lang][el.dataset.i18n];if(value)el.textContent=value});
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el=>{const value=translations[state.lang][el.dataset.i18nPlaceholder];if(value)el.placeholder=value});
  document.querySelectorAll('[data-lang]').forEach(button=>button.classList.toggle('active',button.dataset.lang===state.lang));
  updateMapToolLanguage();renderLayerButtons();if(state.active)activate(state.active.id,false)
}
function renderLayerButtons(){
  const list=document.getElementById('layer-list');list.innerHTML='';
  const order=['complete','enso','terrain'];
  const makeButton=layer=>{const words=localizedLayer(layer);const button=document.createElement('button');button.className='layer-button';button.type='button';button.dataset.id=layer.id;button.innerHTML=`<strong>${words[0]}</strong><small>${words[1]}</small>`;button.addEventListener('click',()=>activate(layer.id,false));return button};
  order.forEach(group=>{
    const layers=state.catalog.filter(layer=>(layer.group||'complete')===group);if(!layers.length)return;
    const details=document.createElement('details');details.className='layer-group';details.open=group==='complete'||layers.some(layer=>state.active&&layer.id===state.active.id);
    const summary=document.createElement('summary');summary.textContent=translations[state.lang][`group_${group}`]||group;details.appendChild(summary);
    if(group==='periods'||group==='enso'){
      [...new Set(layers.map(layer=>layer.scenario))].forEach(scenario=>{const scenarioLayers=layers.filter(layer=>layer.scenario===scenario);const section=document.createElement('div');section.className='layer-scenario';const heading=document.createElement('p');heading.textContent=state.lang==='pt'?(scenarioLayers[0].scenarioLabelPt||scenarioLayers[0].scenarioLabel):scenarioLayers[0].scenarioLabel;section.appendChild(heading);scenarioLayers.forEach(layer=>section.appendChild(makeButton(layer)));details.appendChild(section)})
    }else layers.forEach(layer=>details.appendChild(makeButton(layer)));
    list.appendChild(details)
  })
}
function activate(id,fit=false){
  const layer=state.catalog.find(item=>item.id===id);if(!layer)return;state.active=layer;
  if(state.overlay)map.removeLayer(state.overlay);
  state.overlay=L.imageOverlay(layer.url,layer.bounds,{opacity:state.opacity,interactive:false,className:'scientific-overlay'}).addTo(map);
  if(fit)map.fitBounds(layer.bounds,{padding:[18,18]});
  document.querySelectorAll('.layer-button').forEach(button=>button.classList.toggle('active',button.dataset.id===id));
  const words=localizedLayer(layer);
  document.getElementById('layer-title').textContent=words[0];document.getElementById('layer-subtitle').textContent=words[1];
  document.getElementById('layer-range').textContent=`${fmt(layer.displayMin)}–${fmt(layer.displayMax)} ${layer.units}`;
  document.getElementById('layer-grid').textContent=`${layer.nativeWidth.toLocaleString()} × ${layer.nativeHeight.toLocaleString()}`;
  document.getElementById('layer-coverage').textContent=`${layer.validPercent.toFixed(1)}% ${translations[state.lang].valid_cells}`;
  document.getElementById('layer-status').textContent=words[2];
  const download=document.getElementById('layer-download'),contract=downloadContract(layer),downloadLabel=download.querySelector('[data-download-label]'),downloadNote=document.getElementById('layer-download-note');
  download.href=contract.href;download.target='_blank';download.rel='noopener noreferrer';download.removeAttribute('download');download.dataset.kind=contract.kind;
  if(downloadLabel)downloadLabel.textContent=translations[state.lang][contract.label];
  if(downloadNote)downloadNote.textContent=translations[state.lang][contract.note];
  document.getElementById('legend').innerHTML=`<div class="legend-title">${words[0]} · ${layer.units}</div><div class="legend-ramp" style="background:${palettes[layer.palette]}"></div><div class="legend-labels"><span>${fmt(layer.displayMin)}</span><span>${fmt(layer.displayMax)}</span></div>`;
  if(state.selectionLayer)analyzeSelection(state.selectionLayer)
}

const datalist=document.getElementById('known-places');
places.forEach(([name])=>{const option=document.createElement('option');option.value=name;datalist.appendChild(option)});
function showPlace(name,lat,lon){
  map.setView([lat,lon],10,{animate:true});
  if(state.marker)map.removeLayer(state.marker);
  state.marker=L.circleMarker([lat,lon],{radius:7,color:'#fff',weight:2,fillColor:'#276fbf',fillOpacity:1}).addTo(map).bindTooltip(name,{permanent:false,direction:'top'}).openTooltip();
  document.getElementById('search-message').textContent=`${translations[state.lang].place_found}: ${name}`;
}
document.getElementById('place-search').addEventListener('submit',async event=>{
  event.preventDefault();const query=document.getElementById('place-input').value.trim();if(!query)return;
  const local=places.find(([name])=>name.toLocaleLowerCase().includes(query.toLocaleLowerCase())||query.toLocaleLowerCase().includes(name.split(',')[0].toLocaleLowerCase()));
  if(local){showPlace(...local);return}
  const message=document.getElementById('search-message');message.textContent='…';
  try{
    const response=await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&countrycodes=br&limit=1&q=${encodeURIComponent(query)}`);
    const result=await response.json();if(!result.length)throw new Error('not found');showPlace(result[0].display_name,Number(result[0].lat),Number(result[0].lon));
  }catch(_error){message.textContent=translations[state.lang].place_not_found}
});

const analysisLayers=L.featureGroup().addTo(map);
function analysisMessage(value){document.getElementById('analysis-loading').textContent=value||''}
function loadAnalysisGrid(id){
  if(state.analysisCache[id])return Promise.resolve(state.analysisCache[id]);
  if(state.analysisPromises[id])return state.analysisPromises[id];
  const manifest=(window.FROST_ANALYSIS_MANIFEST||{})[id];
  if(!manifest)return Promise.reject(new Error(`Missing numerical grid for ${id}`));
  state.analysisPromises[id]=new Promise((resolve,reject)=>{
    const finish=()=>{
      const grid=(window.FROST_ANALYSIS_GRIDS||{})[id];
      if(!grid){reject(new Error(`Numerical grid did not register: ${id}`));return}
      const raw=atob(grid.data);const values=new Uint16Array(raw.length/2);
      for(let i=0;i<values.length;i++)values[i]=raw.charCodeAt(i*2)|(raw.charCodeAt(i*2+1)<<8);
      const decoded={...grid,values};delete decoded.data;state.analysisCache[id]=decoded;resolve(decoded)
    };
    if((window.FROST_ANALYSIS_GRIDS||{})[id]){finish();return}
    const script=document.createElement('script');script.src=manifest.url;script.onload=finish;script.onerror=()=>reject(new Error(`Could not load ${manifest.url}`));document.head.appendChild(script)
  }).finally(()=>{delete state.analysisPromises[id]});
  return state.analysisPromises[id]
}
function gridValue(grid,index){const encoded=grid.values[index];if(encoded===grid.nodata)return null;return grid.minimum+(encoded/grid.quantizedMaximum)*(grid.maximum-grid.minimum)}
function mercatorY(lat){const clipped=Math.max(-85.05112878,Math.min(85.05112878,lat))*Math.PI/180;return Math.log(Math.tan(Math.PI/4+clipped/2))}
function gridRow(grid,lat){
  const [[south],[north]]=grid.bounds;
  if(grid.projection==='EPSG:3857')return(mercatorY(north)-mercatorY(lat))/(mercatorY(north)-mercatorY(south))*grid.height;
  return(north-lat)/(north-south)*grid.height
}
function gridLatitude(grid,row){
  const [[south],[north]]=grid.bounds;
  if(grid.projection==='EPSG:3857'){const y=mercatorY(north)-(row/grid.height)*(mercatorY(north)-mercatorY(south));return(2*Math.atan(Math.exp(y))-Math.PI/2)*180/Math.PI}
  return north-(row/grid.height)*(north-south)
}
function samplePoint(grid,lat,lon){
  const [[south,west],[north,east]]=grid.bounds;if(lat<south||lat>north||lon<west||lon>east)return null;
  const x=Math.min(grid.width-1,Math.max(0,Math.floor((lon-west)/(east-west)*grid.width)));
  const y=Math.min(grid.height-1,Math.max(0,Math.floor(gridRow(grid,lat))));
  const value=gridValue(grid,y*grid.width+x);return value===null?null:{value,x,y}
}
function pointInRing(lon,lat,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){
  const [xi,yi]=ring[i],[xj,yj]=ring[j];const crosses=((yi>lat)!==(yj>lat))&&(lon<(xj-xi)*(lat-yi)/(yj-yi)+xi);if(crosses)inside=!inside
}return inside}
function polygonAreaKm2(ring){
  const earth=6371.0088;const meanLat=ring.reduce((sum,item)=>sum+item[1],0)/ring.length*Math.PI/180;let twiceArea=0;
  for(let i=0;i<ring.length;i++){const a=ring[i],b=ring[(i+1)%ring.length];const ax=earth*a[0]*Math.PI/180*Math.cos(meanLat),ay=earth*a[1]*Math.PI/180;const bx=earth*b[0]*Math.PI/180*Math.cos(meanLat),by=earth*b[1]*Math.PI/180;twiceArea+=ax*by-bx*ay}
  return Math.abs(twiceArea)/2
}
function paletteColor(name,t){
  const ramps={RdYlBu:['#a50026','#f46d43','#ffffbf','#74add1','#313695'],RdYlBu_r:['#313695','#74add1','#ffffbf','#f46d43','#a50026'],viridis:['#440154','#3b528b','#21918c','#5ec962','#fde725'],gist_earth:['#17336b','#478d82','#a9b26f','#c49a6c','#f5f2ed']};
  const colors=ramps[name]||ramps.viridis;const p=Math.max(0,Math.min(1,t))*(colors.length-1);const index=Math.min(colors.length-2,Math.floor(p)),mix=p-index;
  const rgb=hex=>[1,3,5].map(start=>parseInt(hex.slice(start,start+2),16));const a=rgb(colors[index]),b=rgb(colors[index+1]);return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*mix)).join(',')})`
}
function drawHistogram(values,layer){
  const canvas=document.getElementById('selection-chart'),rect=canvas.getBoundingClientRect(),ratio=Math.min(2,window.devicePixelRatio||1);canvas.width=Math.max(260,Math.round(rect.width*ratio));canvas.height=Math.round(112*ratio);const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
  const width=canvas.width/ratio,height=canvas.height/ratio;ctx.clearRect(0,0,width,height);const bins=14,minimum=values[0],maximum=values[values.length-1],counts=Array(bins).fill(0),span=maximum-minimum||1;
  values.forEach(value=>counts[Math.min(bins-1,Math.floor((value-minimum)/span*bins))]++);const peak=Math.max(...counts,1),gap=2,barWidth=(width-18-(bins-1)*gap)/bins;
  counts.forEach((count,index)=>{const barHeight=(height-28)*count/peak;ctx.fillStyle=paletteColor(layer.palette,(index+.5)/bins);ctx.fillRect(9+index*(barWidth+gap),height-18-barHeight,barWidth,barHeight)});
  ctx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--muted').trim()||'#65716e';ctx.font='10px Inter, sans-serif';ctx.textAlign='left';ctx.fillText(fmt(minimum),8,height-5);ctx.textAlign='right';ctx.fillText(fmt(maximum),width-8,height-5)
}
async function analyzeSelection(layer){
  if(!state.active||!layer)return;analysisMessage(translations[state.lang].loading_values);
  try{
    const grid=await loadAnalysisGrid(state.active.id),geometry=layer.toGeoJSON().geometry,ring=geometry.coordinates[0];
    const lons=ring.map(item=>item[0]),lats=ring.map(item=>item[1]),minLon=Math.min(...lons),maxLon=Math.max(...lons),minLat=Math.min(...lats),maxLat=Math.max(...lats),[[south,west],[north,east]]=grid.bounds;
    const x0=Math.max(0,Math.floor((minLon-west)/(east-west)*grid.width)),x1=Math.min(grid.width-1,Math.ceil((maxLon-west)/(east-west)*grid.width));
    const y0=Math.max(0,Math.floor(gridRow(grid,maxLat))),y1=Math.min(grid.height-1,Math.ceil(gridRow(grid,minLat)));
    const candidateCount=Math.max(0,x1-x0+1)*Math.max(0,y1-y0+1),stride=Math.max(1,Math.ceil(Math.sqrt(candidateCount/150000))),samples=[];
    for(let y=y0;y<=y1;y+=stride){const lat=gridLatitude(grid,y+.5);for(let x=x0;x<=x1;x+=stride){const lon=west+(x+.5)/grid.width*(east-west);if(!pointInRing(lon,lat,ring))continue;const value=gridValue(grid,y*grid.width+x);if(value!==null)samples.push({lat,lon,value})}}
    if(!samples.length)throw new Error(translations[state.lang].no_valid_values);
    const values=samples.map(item=>item.value).sort((a,b)=>a-b),mean=values.reduce((a,b)=>a+b,0)/values.length,median=values.length%2?values[(values.length-1)/2]:(values[values.length/2-1]+values[values.length/2])/2;
    const stats={area:polygonAreaKm2(ring),count:values.length,min:values[0],mean,median,max:values[values.length-1],stride};state.selectionSamples=samples;state.selectionStats=stats;
    document.getElementById('selection-empty').hidden=true;document.getElementById('selection-results').hidden=false;document.getElementById('selection-area').textContent=`${stats.area.toLocaleString(undefined,{maximumFractionDigits:1})} km²`;document.getElementById('selection-count').textContent=stats.count.toLocaleString();
    for(const key of ['min','mean','median','max'])document.getElementById(`selection-${key}`).textContent=`${fmt(stats[key])} ${state.active.units}`;
    drawHistogram(values,state.active);analysisMessage('')
  }catch(error){state.selectionSamples=[];state.selectionStats=null;document.getElementById('selection-results').hidden=true;document.getElementById('selection-empty').hidden=false;document.getElementById('selection-empty').textContent=error.message;analysisMessage('')}
}
function startDrawing(kind){
  if(!L.Draw){analysisMessage('Drawing tools require an internet connection.');return}
  const options={shapeOptions:{color:'#f3b63f',weight:2,fillColor:'#f3b63f',fillOpacity:.12}};const drawer=kind==='rectangle'?new L.Draw.Rectangle(map,options):kind==='circle'?new L.Draw.Circle(map,options):new L.Draw.Polygon(map,{...options,allowIntersection:false,showArea:true});drawer.enable()
}
map.on('draw:drawstart',()=>{state.drawing=true});map.on('draw:drawstop',()=>{setTimeout(()=>{state.drawing=false},0)});
map.on('draw:created',event=>{analysisLayers.clearLayers();state.selectionLayer=event.layer;analysisLayers.addLayer(event.layer);analyzeSelection(event.layer)});
map.on('click',async event=>{
  if(state.drawing||!state.active)return;analysisMessage(translations[state.lang].loading_values);
  try{const grid=await loadAnalysisGrid(state.active.id),sample=samplePoint(grid,event.latlng.lat,event.latlng.lng),words=localizedLayer(state.active);const value=sample?`${fmt(sample.value)} ${state.active.units}`:translations[state.lang].no_valid_values;
    L.popup({className:'map-value-popup'}).setLatLng(event.latlng).setContent(`<strong>${translations[state.lang].point_value}: ${value}</strong><span>${words[0]}</span><span>${translations[state.lang].coordinates}: ${event.latlng.lat.toFixed(5)}, ${event.latlng.lng.toFixed(5)}</span>`).openOn(map)
  }catch(error){analysisMessage(error.message);return}analysisMessage('')
});
document.getElementById('draw-rectangle').addEventListener('click',()=>startDrawing('rectangle'));document.getElementById('draw-circle').addEventListener('click',()=>startDrawing('circle'));document.getElementById('draw-polygon').addEventListener('click',()=>startDrawing('polygon'));
document.getElementById('clear-selection').addEventListener('click',()=>{analysisLayers.clearLayers();state.selectionLayer=null;state.selectionSamples=[];state.selectionStats=null;document.getElementById('selection-results').hidden=true;document.getElementById('selection-empty').hidden=false;document.getElementById('selection-empty').textContent=translations[state.lang].no_selection;map.closePopup()});
function saveBlob(name,type,content){const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([content],{type}));link.download=name;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),1000)}
document.getElementById('export-csv').addEventListener('click',()=>{if(!state.selectionSamples.length)return;const rows=['latitude,longitude,value,units',...state.selectionSamples.map(item=>`${item.lat.toFixed(6)},${item.lon.toFixed(6)},${item.value.toFixed(6)},${state.active.units}`)];saveBlob(`${state.active.id}_selection.csv`,'text/csv;charset=utf-8',rows.join('\n'))});
document.getElementById('export-geojson').addEventListener('click',()=>{if(!state.selectionLayer||!state.selectionStats)return;const feature=state.selectionLayer.toGeoJSON();feature.properties={layer:state.active.id,units:state.active.units,...state.selectionStats};saveBlob(`${state.active.id}_selection.geojson`,'application/geo+json',JSON.stringify(feature,null,2))});

if(!state.catalog.length){document.getElementById('layer-list').innerHTML='<p class="layer-status">Map catalog is unavailable.</p>';map.setView([-25,-51],5)}else{renderLanguage();activate(state.catalog[0].id,true)}
document.getElementById('opacity').addEventListener('input',event=>{state.opacity=Number(event.target.value)/100;document.getElementById('opacity-value').textContent=`${event.target.value}%`;if(state.overlay)state.overlay.setOpacity(state.opacity)});
document.querySelectorAll('[data-lang]').forEach(button=>button.addEventListener('click',()=>{state.lang=button.dataset.lang;localStorage.setItem('frost-lang',state.lang);renderLanguage()}));
document.getElementById('theme-toggle').addEventListener('click',()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=theme;localStorage.setItem('frost-theme',theme);updateBasemap()});

document.querySelectorAll('.collection-card[data-target]').forEach(card=>{
  const openCollection=()=>document.querySelector(card.dataset.target)?.scrollIntoView({behavior:'smooth',block:'start'});
  card.tabIndex=0;card.setAttribute('role','link');
  card.addEventListener('click',event=>{if(!event.target.closest('a'))openCollection()});
  card.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openCollection()}})
});

document.querySelectorAll('.collection-card[data-href]').forEach(card=>{
  const openCollection=()=>{window.location.href=card.dataset.href};
  card.tabIndex=0;card.setAttribute('role','link');
  card.addEventListener('click',event=>{if(!event.target.closest('a'))openCollection()});
  card.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openCollection()}})
});
const collectionRail=document.querySelector('.collection-grid');
const scrollCollections=direction=>collectionRail?.scrollBy({left:direction*Math.min(collectionRail.clientWidth*.86,460),behavior:'smooth'});
document.getElementById('collections-previous')?.addEventListener('click',()=>scrollCollections(-1));
document.getElementById('collections-next')?.addEventListener('click',()=>scrollCollections(1));
