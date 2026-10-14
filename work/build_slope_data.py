from pathlib import Path
import csv, json, math, time
import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions(); ogr.UseExceptions(); osr.UseExceptions()
ROOT=Path(__file__).resolve().parent.parent
WORK=ROOT/'work'; OUT=ROOT/'outputs'/'hallasan_slope'
OUT.mkdir(parents=True,exist_ok=True)
SHAPES=OUT/'shapefiles'; SHAPES.mkdir(exist_ok=True)
SOURCE=ROOT/'inputs/reference/hallasan_course_cells.gpkg'
region=json.loads((WORK/'slope_region.json').read_text(encoding='utf-8'))
def srs(epsg):
    s=osr.SpatialReference(); s.ImportFromEPSG(epsg); s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER); return s
UTM=srs(32652); WGS=srs(4326)
src=ogr.Open(str(SOURCE),0)
sl=src.GetLayerByName('candidate_lcc_grid_500m')
LCC=sl.GetSpatialRef().Clone(); LCC.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
to_utm=osr.CoordinateTransformation(LCC,UTM)
to_wgs=osr.CoordinateTransformation(UTM,WGS)
def rect(xmin,ymin,xmax,ymax):
    r=ogr.Geometry(ogr.wkbLinearRing)
    for x,y in [(xmin,ymin),(xmax,ymin),(xmax,ymax),(xmin,ymax),(xmin,ymin)]: r.AddPoint_2D(x,y)
    p=ogr.Geometry(ogr.wkbPolygon); p.AddGeometry(r); return p
e=sl.GetExtent()
boundary=rect(e[0],e[2],e[1],e[3]); boundary.Segmentize(25); boundary.Transform(to_utm)
grids=[]
for f in sl:
    g=f.GetGeometryRef().Clone(); g.Segmentize(25); g.Transform(to_utm)
    grids.append({'id':f['ref_id'],'i':int(f['i_assumed']),'j':int(f['j_assumed']),'g':g})
grids.sort(key=lambda q:(q['j'],q['i']))
assert len(grids)==1849 and len({q['id'] for q in grids})==1849
b=region['bounds_by_epsg']['32652']
pad=240
b=[math.floor((b[0]-pad)/30)*30,math.floor((b[1]-pad)/30)*30,math.ceil((b[2]+pad)/30)*30,math.ceil((b[3]+pad)/30)*30]
opts=['COMPRESS=DEFLATE','TILED=YES','PREDICTOR=3']
dem_full=WORK/'dem_utm_buffer.tif'
dem=gdal.Warp(str(dem_full),str(WORK/'public_sources/copernicus_N33_E126.tif'),dstSRS=UTM.ExportToWkt(),outputBounds=b,xRes=30,yRes=30,resampleAlg='bilinear',dstNodata=-9999,format='GTiff',creationOptions=opts)
dem.GetRasterBand(1).SetUnitType('m'); dem.FlushCache()
slope_ds=gdal.DEMProcessing(str(WORK/'slope_full.tif'),dem,'slope',alg='Horn',slopeFormat='degree',scale=1,computeEdges=False,creationOptions=opts)
aspect_ds=gdal.DEMProcessing(str(WORK/'aspect_full.tif'),dem,'aspect',alg='Horn',computeEdges=False,creationOptions=opts)
elev=dem.ReadAsArray(); slope=slope_ds.ReadAsArray(); aspect=aspect_ds.ReadAsArray()
gt=dem.GetGeoTransform(); h,w=slope.shape
valid=np.isfinite(slope)&(slope>=0)&(slope<=90)&(elev!=-9999)
classes=np.zeros_like(slope,dtype=np.uint8)
classes[valid]=np.minimum((slope[valid]//5).astype(np.uint8)+1,10)
print('RASTER_READY',w,h,'slope_range',float(slope[valid].min()),float(slope[valid].max()),flush=True)

def make_layer(name,geom_type,fields):
    ds=ogr.GetDriverByName('ESRI Shapefile').CreateDataSource(str(SHAPES/(name+'.shp')))
    layer=ds.CreateLayer(name,UTM,geom_type,options=['ENCODING=UTF-8'])
    for name,kind in fields:
        fld=ogr.FieldDefn(name,kind)
        if kind==ogr.OFTString: fld.SetWidth(40)
        if kind==ogr.OFTReal: fld.SetWidth(22); fld.SetPrecision(6)
        layer.CreateField(fld)
    return ds,layer

field_types=[('grid_id',ogr.OFTString),('i_ref',ogr.OFTInteger),('j_ref',ogr.OFTInteger),('lon',ogr.OFTReal),('lat',ogr.OFTReal),('area_m2',ogr.OFTReal),('valid_m2',ogr.OFTReal),('cover_pct',ogr.OFTReal),('n_px',ogr.OFTInteger),('mean_deg',ogr.OFTReal),('p90_deg',ogr.OFTReal),('max_deg',ogr.OFTReal),('min_deg',ogr.OFTReal),('sd_deg',ogr.OFTReal),('mean_pct',ogr.OFTReal),('elev_mean',ogr.OFTReal),('elev_min',ogr.OFTReal),('elev_max',ogr.OFTReal),('asp_deg',ogr.OFTReal),('asp_r',ogr.OFTReal)]
class_fields=[f'p{5*i:02}_{5*(i+1):02}' if i<9 else 'p45_plus' for i in range(10)]
field_types += [(k,ogr.OFTReal) for k in class_fields]+[('src_m',ogr.OFTInteger),('source',ogr.OFTString),('method',ogr.OFTString)]
grid_ds,grid_layer=make_layer('grid_slope_500m',ogr.wkbPolygon,field_types)
rows=[]; summary=[]; begin=time.time()
for k,q in enumerate(grids):
    g=q['g']; xmin,xmax,ymin,ymax=g.GetEnvelope()
    c0=max(0,int(math.floor((xmin-gt[0])/30))); c1=min(w,int(math.ceil((xmax-gt[0])/30)))
    r0=max(0,int(math.floor((gt[3]-ymax)/30))); r1=min(h,int(math.ceil((gt[3]-ymin)/30)))
    vals=[]; areas=[]; zs=[]; az=[]; cls=[]; cnt=0
    for r in range(r0,r1):
        ytop=gt[3]-r*30
        for c in range(c0,c1):
            if not valid[r,c]: continue
            xleft=gt[0]+c*30
            pix=rect(xleft,ytop-30,xleft+30,ytop)
            if g.Contains(pix): area=900.0
            elif g.Intersects(pix): area=g.Intersection(pix).Area()
            else: continue
            if area<=1e-7: continue
            vals.append(float(slope[r,c])); areas.append(area); zs.append(float(elev[r,c])); az.append(float(aspect[r,c])); cls.append(int(classes[r,c])); cnt+=1
    v=np.array(vals); a=np.array(areas); z=np.array(zs); az=np.array(az); cl=np.array(cls)
    total=g.Area(); va=a.sum()
    assert va>0
    mean=np.average(v,weights=a); order=np.argsort(v); p90=v[order][np.searchsorted(np.cumsum(a[order]),va*.9)]
    am=az>=0
    av=np.sum(a[am]*np.cos(np.deg2rad(az[am]))); bv=np.sum(a[am]*np.sin(np.deg2rad(az[am])))
    ar=math.hypot(av,bv)/a[am].sum() if am.any() else 0
    ad=math.degrees(math.atan2(bv,av))%360 if ar>1e-8 else None
    cen=g.Centroid(); cen.Transform(to_wgs)
    row={'grid_id':q['id'],'i_ref':q['i'],'j_ref':q['j'],'lon':cen.GetX(),'lat':cen.GetY(),'area_m2':total,'valid_m2':float(va),'cover_pct':float(va/total*100),'n_px':cnt,'mean_deg':float(mean),'p90_deg':float(p90),'max_deg':float(v.max()),'min_deg':float(v.min()),'sd_deg':float(np.sqrt(np.average((v-mean)**2,weights=a))),'mean_pct':float(np.average(np.tan(np.deg2rad(v))*100,weights=a)),'elev_mean':float(np.average(z,weights=a)),'elev_min':float(z.min()),'elev_max':float(z.max()),'asp_deg':ad,'asp_r':ar}
    for ci,name in enumerate(class_fields): row[name]=float(a[cl==ci+1].sum()/va*100)
    row.update(src_m=30,source='Copernicus GLO-30 DSM',method='GDAL Horn; area weighted')
    feat=ogr.Feature(grid_layer.GetLayerDefn()); feat.SetGeometry(g)
    for name,value in row.items():
        if value is not None: feat.SetField(name,value)
    grid_layer.CreateFeature(feat)
    rows.append(row)
    if (k+1)%300==0: print('GRID_STATS',k+1,'/',len(grids),'seconds',round(time.time()-begin,1),flush=True)
grid_ds=None
with (OUT/'hallasan_grid_slope.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=[x[0] for x in field_types]); writer.writeheader(); writer.writerows(rows)
print('GRID_CSV_COMPLETE',len(rows),flush=True)

mem=gdal.GetDriverByName('MEM').Create('',w,h,1,gdal.GDT_Byte); mem.SetGeoTransform(gt); mem.SetProjection(UTM.ExportToWkt()); mem.GetRasterBand(1).WriteArray(classes); mem.GetRasterBand(1).SetNoDataValue(0)
poly_mem=ogr.GetDriverByName('Memory').CreateDataSource('temp'); poly_layer=poly_mem.CreateLayer('classes',UTM,ogr.wkbPolygon); poly_layer.CreateField(ogr.FieldDefn('class_id',ogr.OFTInteger))
gdal.Polygonize(mem.GetRasterBand(1),mem.GetRasterBand(1).GetMaskBand(),poly_layer,0,[],callback=None)
poly_ds,poly_out=make_layer('slope_classes',ogr.wkbPolygon,[('poly_id',ogr.OFTInteger),('class_id',ogr.OFTInteger),('deg_lo',ogr.OFTInteger),('deg_hi',ogr.OFTInteger),('class_txt',ogr.OFTString),('area_m2',ogr.OFTReal),('source',ogr.OFTString)])
area_classes=np.zeros(10); poly_count=0
for ft in poly_layer:
    g=ft.GetGeometryRef()
    if not g.Intersects(boundary): continue
    g=g.Intersection(boundary)
    if g.IsEmpty() or g.Area()<=1e-6: continue
    ci=ft['class_id']; area=g.Area(); area_classes[ci-1]+=area; poly_count+=1
    nf=ogr.Feature(poly_out.GetLayerDefn()); nf.SetGeometry(g)
    for key,value in {'poly_id':poly_count,'class_id':ci,'deg_lo':(ci-1)*5,'deg_hi':ci*5 if ci<10 else 90,'class_txt':f'{(ci-1)*5}-{ci*5} deg' if ci<10 else '45+ deg','area_m2':area,'source':'Copernicus GLO-30 DSM'}.items(): nf.SetField(key,value)
    poly_out.CreateFeature(nf)
poly_ds=None
print('SLOPE_POLYGONS',poly_count,flush=True)

boundary_ds,boundary_layer=make_layer('study_boundary',ogr.wkbPolygon,[('name',ogr.OFTString),('area_m2',ogr.OFTReal)])
bf=ogr.Feature(boundary_layer.GetLayerDefn()); bf.SetGeometry(boundary); bf['name']='Hallasan full reference grid'; bf['area_m2']=boundary.Area(); boundary_layer.CreateFeature(bf); boundary_ds=None
for table,name in [('trails','reference_trails'),('park','reference_park'),('labels','reference_labels')]:
    gdal.VectorTranslate(str(SHAPES/(name+'.shp')),str(SOURCE),format='ESRI Shapefile',layers=[table],dstSRS=UTM.ExportToWkt(),layerCreationOptions=['ENCODING=UTF-8'])

# Raster clipping follows pixel-centre convention; vector statistics above use exact intersection area.
dem.FlushCache(); slope_ds.FlushCache(); aspect_ds.FlushCache()
boundary_file=str(SHAPES/'study_boundary.shp')
for source,name,unit in [(str(dem_full),'dem_30m.tif','m'),(str(WORK/'slope_full.tif'),'slope_degrees_30m.tif','degree'),(str(WORK/'aspect_full.tif'),'aspect_degrees_30m.tif','degree')]:
    d=gdal.Warp(str(OUT/name),source,cutlineDSName=boundary_file,cropToCutline=True,dstNodata=-9999,xRes=30,yRes=30,targetAlignedPixels=True,creationOptions=opts)
    d.GetRasterBand(1).SetUnitType(unit); d.FlushCache(); d=None

overall_area=sum(r['valid_m2'] for r in rows)
overall_mean=sum(r['mean_deg']*r['valid_m2'] for r in rows)/overall_area
for ci in range(10): summary.append({'class_id':ci+1,'min_deg':ci*5,'max_deg':(ci+1)*5 if ci<9 else 90,'area_m2':float(area_classes[ci]),'area_pct':float(area_classes[ci]/area_classes.sum()*100)})
with (OUT/'hallasan_slope_classes.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(summary[0])); writer.writeheader(); writer.writerows(summary)
assert abs(area_classes.sum()-boundary.Area())/boundary.Area()<1e-7
assert min(r['cover_pct'] for r in rows)>99.999
assert max(abs(sum(r[key] for key in class_fields)-100) for r in rows)<1e-8
validation={'grid_count':len(rows),'unique_grid_ids':len(set(r['grid_id'] for r in rows)),'slope_polygon_count':poly_count,'area_utm_m2':boundary.Area(),'source_lcc_area_m2':1849*250000,'slope_polygon_area_m2':float(area_classes.sum()),'area_coverage_min_pct':min(r['cover_pct'] for r in rows),'area_coverage_max_pct':max(r['cover_pct'] for r in rows),'overall_mean_slope_degrees':overall_mean,'maximum_slope_degrees':max(r['max_deg'] for r in rows),'elevation_range_m':[min(r['elev_min'] for r in rows),max(r['elev_max'] for r in rows)],'classes':summary,'raster_shape_buffered':[h,w],'crs':'EPSG:32652','grid_source_crs':LCC.ExportToProj4(),'method':'Copernicus GLO-30 DSM; bilinear reprojection to 30m UTM52; GDAL Horn slope; exact pixel/grid intersection area weighting','source_warning':'Not VWorld analysis output. DSM includes vegetation and structures. Original 500m LCC reference grid alignment to official radar is unverified.','nodata':-9999,'statistics_status':'passed'}
(OUT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
print('ANALYSIS_COMPLETE',json.dumps({k:v for k,v in validation.items() if k not in ['classes','grid_source_crs']}),flush=True)
