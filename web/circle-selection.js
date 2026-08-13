(function(){
  if(!window.L||!L.Circle)return;
  const original=L.Circle.prototype.toGeoJSON;
  L.Circle.prototype.toGeoJSON=function(){
    const center=this.getLatLng(),radius=this.getRadius();
    if(!Number.isFinite(radius)||radius<=0)return original.call(this);
    const earth=6371008.8,lat1=center.lat*Math.PI/180,lon1=center.lng*Math.PI/180;
    const angular=radius/earth,ring=[];
    for(let i=0;i<=96;i++){
      const bearing=2*Math.PI*i/96;
      const lat2=Math.asin(Math.sin(lat1)*Math.cos(angular)+Math.cos(lat1)*Math.sin(angular)*Math.cos(bearing));
      const lon2=lon1+Math.atan2(Math.sin(bearing)*Math.sin(angular)*Math.cos(lat1),Math.cos(angular)-Math.sin(lat1)*Math.sin(lat2));
      ring.push([lon2*180/Math.PI,lat2*180/Math.PI]);
    }
    return {type:'Feature',properties:{radius_m:radius},geometry:{type:'Polygon',coordinates:[ring]}};
  };
})();
