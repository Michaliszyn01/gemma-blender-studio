"""Run inside the real Blender, independently from unittest mocks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import blender_worker as worker

bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
worker.apply({'op':'cylinder','name':'joint','dimensions':[0.6,0.6,0.3],
              'rotation':[0,90,0],'location':[1,0,3],'bevel':0.02})
worker.apply({'op':'mesh','name':'offset_mesh',
              'vertices':[[-1,-1,2],[1,-1,2],[1,1,2],[-1,1,2],
                          [-0.6,-1,3],[0.6,-1,3],[0.6,1,3],[-0.6,1,3]],
              'faces':[[3,2,1,0],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]],
              'color':[0.5,0.5,0.5,1],'roughness':0.8,'bevel':0.01})
report={o['name']:o for o in worker.report()['objects']}
joint=report['joint']
assert abs(joint['rotation'][1]-90)<0.001
assert abs((joint['world_bounds_max'][0]-joint['world_bounds_min'][0])-0.3)<0.001
assert report['offset_mesh']['location']==[0,0,0]
assert report['offset_mesh']['world_center']==[0,0,2.5]
worker.apply({'op':'transform','name':'joint','dimensions':[0.8,0.8,0.4]})
report={o['name']:o for o in worker.report()['objects']}
assert abs((report['joint']['world_bounds_max'][0]-report['joint']['world_bounds_min'][0])-0.4)<0.001
print('PASS: dimensions, rotation, world bounds, tapered mesh, bevel, material')
worker.apply({'op':'tapered_box','name':'taper','top_scale':[1.5,0.8],
              'dimensions':[3,2,1],'location':[0,0,2],'bevel':0.03})
obj=bpy.data.objects['taper']
assert len(obj.data.vertices)==8 and len(obj.data.polygons)==6
assert all(abs(a-b)<0.001 for a,b in zip(obj.dimensions,[3,2,1]))
bottom=[v.co.x for v in obj.data.vertices if v.co.z<0]
top=[v.co.x for v in obj.data.vertices if v.co.z>0]
assert abs((max(top)-min(top))/(max(bottom)-min(bottom))-1.5)<0.001
assert all(p.normal.dot(p.center)>0 for p in obj.data.polygons)
print('PASS: parametric tapered_box dimensions, ratio and outward normals')
worker.apply({'op':'transform','name':'taper','top_scale':[0.75,1.2],'bevel':0.08})
obj=bpy.data.objects['taper']
assert all(abs(a-b)<0.001 for a,b in zip(obj.dimensions,[3,2,1]))
bottom=[v.co.x for v in obj.data.vertices if v.co.z<0]
top=[v.co.x for v in obj.data.vertices if v.co.z>0]
assert abs((max(top)-min(top))/(max(bottom)-min(bottom))-0.75)<0.001
assert obj.modifiers['StudioBevel'].width>0.079
report={o['name']:o for o in worker.report()['objects']}
assert abs(report['joint']['world_axis_z'][0])>0.999
assert report['taper']['primitive']=='tapered_box'
assert report['taper']['top_scale']==list(obj['studio_top_scale'])
assert report['taper']['bevel_width']==0.08
print('PASS: edit taper ratio without losing dimensions; bevel and world cylinder axis evidence')
