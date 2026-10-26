"""Run only inside Blender: --background --disable-autoexec --python this.py -- request.json"""
import json
import math
import re
import unicodedata
from pathlib import Path
import sys
import bpy
from mathutils import Vector


def descendants(root):
    return [root]+list(root.children_recursive)


def asset_import(path, name):
    before=set(bpy.data.objects)
    ext=Path(path).suffix.lower()
    if ext=='.glb':
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext=='.fbx':
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext=='.obj':
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError('Formato de asset inválido.')
    added=[o for o in bpy.data.objects if o not in before]
    if not added:
        raise ValueError('Asset sem objetos.')
    group=bpy.data.objects.new(name,None)
    bpy.context.collection.objects.link(group)
    group['studio_group']=True
    for o in added:
        if o.parent not in added:
            matrix=o.matrix_world.copy();o.parent=group;o.matrix_world=matrix
    return group


def set_dimensions(obj, values):
    bpy.context.view_layer.update()
    if obj.type!='EMPTY':
        obj.dimensions=values
        bpy.context.view_layer.update()
        bpy.context.view_layer.objects.active=obj
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True)
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    else:
        bpy.context.view_layer.update()
        verts=[o.matrix_world@Vector(v) for o in obj.children_recursive if o.type=='MESH' for v in o.bound_box]
        if not verts:
            raise ValueError('Grupo sem geometria.')
        size=[max(v[i] for v in verts)-min(v[i] for v in verts) for i in range(3)]
        obj.scale=[obj.scale[i]*values[i]/max(size[i],0.001) for i in range(3)]


def tapered_mesh(name,scale):
    sx,sy=scale
    mx,my=max(1,sx),max(1,sy)
    corners=[(-0.5,-0.5),(0.5,-0.5),(0.5,0.5),(-0.5,0.5)]
    vertices=[(x/mx,y/my,-0.5) for x,y in corners]+[(x*sx/mx,y*sy/my,0.5) for x,y in corners]
    mesh=bpy.data.meshes.new(name+'_mesh')
    mesh.from_pydata(vertices,[],[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
    mesh.update()
    return mesh


def apply(a):
    op=a['op'];name=a['name']
    obj=None
    if op in {'transform','material','delete'}:
        obj=bpy.data.objects.get(name)
        if obj is None:
            raise ValueError('Objeto não existe: '+name)
        if op=='delete':
            for item in reversed(descendants(obj)):
                bpy.data.objects.remove(item,do_unlink=True)
            return
    elif op=='import_asset':
        obj=asset_import(a['asset_path'],name)
    elif op=='tapered_box':
        mesh=tapered_mesh(name,a['top_scale'])
        obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
        obj['studio_top_scale']=a['top_scale']
    elif op=='mesh':
        mesh=bpy.data.meshes.new(name+'_mesh');mesh.from_pydata(a['vertices'],[],a['faces']);mesh.update()
        obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    else:
        if op=='box':bpy.ops.mesh.primitive_cube_add(size=1)
        elif op=='cylinder':bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=0.5,depth=1)
        elif op=='cone':bpy.ops.mesh.primitive_cone_add(vertices=12,radius1=0.5,radius2=0,depth=1)
        elif op=='sphere':bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=0.5)
        elif op=='torus':bpy.ops.mesh.primitive_torus_add(major_segments=24,minor_segments=8,major_radius=0.4,minor_radius=0.1)
        else:raise ValueError('Operação desconhecida.')
        obj=bpy.context.object
    obj.name=name
    if op not in {'transform','material'}:
        obj['studio_primitive']=op
    if op=='transform' and 'top_scale' in a:
        if obj.get('studio_primitive')!='tapered_box':
            raise ValueError('top_scale exige um objeto criado como tapered_box.')
        bpy.context.view_layer.update()
        dimensions=list(obj.dimensions)
        old=obj.data
        obj.data=tapered_mesh(name,a['top_scale'])
        for mat in old.materials:obj.data.materials.append(mat)
        obj['studio_top_scale']=a['top_scale']
        set_dimensions(obj,dimensions)
    if 'dimensions' in a:set_dimensions(obj,a['dimensions'])
    if 'location' in a:obj.location=a['location']
    if 'rotation' in a:obj.rotation_euler=[math.radians(x) for x in a['rotation']]
    meshes=[o for o in descendants(obj) if o.type=='MESH']
    if any(k in a for k in ['color','metallic','roughness']):
        for item in meshes:
            old=item.data.materials[0] if item.data.materials else None
            mat=old.copy() if old else bpy.data.materials.new(name+'_surface')
            mat.use_nodes=True
            bsdf=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
            if bsdf:
                if 'color' in a:bsdf.inputs['Base Color'].default_value=a['color'];mat.diffuse_color=a['color']
                if 'metallic' in a:bsdf.inputs['Metallic'].default_value=a['metallic']
                if 'roughness' in a:bsdf.inputs['Roughness'].default_value=a['roughness']
            item.data.materials.clear();item.data.materials.append(mat)
    if 'bevel' in a:
        for item in meshes:
            mod=item.modifiers.get('StudioBevel') or item.modifiers.new('StudioBevel','BEVEL')
            mod.width=a['bevel'];mod.segments=2


def frame_scene():
    for obj in list(bpy.data.objects):
        if obj.type in {'CAMERA','LIGHT'} or obj.name.startswith('SYS_'):
            bpy.data.objects.remove(obj,do_unlink=True)
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render]
    bpy.context.view_layer.update()
    corners=[o.matrix_world@Vector(v) for o in meshes for v in o.bound_box]
    if not corners:raise ValueError('A cena precisa de geometria visível.')
    low=Vector([min(v[i] for v in corners) for i in range(3)])
    high=Vector([max(v[i] for v in corners) for i in range(3)])
    center=(low+high)/2;size=max(high-low);size=max(size,1)
    scene=bpy.context.scene
    scene.world=bpy.data.worlds.new('SYS_World')
    scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(0.16,0.18,0.22,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=0.7
    for i,offset in enumerate([(1,-2,3),(-2,-1,1),(1,2,2)]):
        data=bpy.data.lights.new('SYS_Light'+str(i),'AREA');data.energy=size*size*50;data.shape='DISK';data.size=size*1.5
        light=bpy.data.objects.new(data.name,data);scene.collection.objects.link(light)
        light.location=center+Vector(offset)*size
        light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('SYS_Camera');cam=bpy.data.objects.new('SYS_Camera',data);scene.collection.objects.link(cam)
    data.type='ORTHO';data.ortho_scale=size*1.45;scene.camera=cam
    # Cycles CPU deliberately avoids competing with Ollama for GPU memory.
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=12
    scene.cycles.use_denoising=True
    scene.render.resolution_x=640;scene.render.resolution_y=640;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
    return cam,center,size


def in_import_group(obj):
    parent=obj.parent
    while parent:
        if parent.get("studio_group"):
            return True
        parent=parent.parent
    return False


def normalize_names():
    # Stable ASCII handles let the model edit objects from any uploaded scene.
    for index,obj in enumerate(list(bpy.context.scene.objects)):
        if obj.name.startswith("SYS_"):
            continue
        name=unicodedata.normalize("NFKD",obj.name).encode("ascii","ignore").decode()
        name=re.sub(r"[^A-Za-z0-9_.-]","_",name)[:48]
        if not name or not name[0].isalpha():
            name="part_"+name
        obj.name=name or f"part_{index:03d}"


def report():
    bpy.context.view_layer.update()
    entries=[];triangles=0
    for obj in bpy.context.scene.objects:
        if obj.type=='MESH':
            obj.data.calc_loop_triangles();triangles+=len(obj.data.loop_triangles)
        if obj.name.startswith('SYS_') or in_import_group(obj):
            continue
        if obj.type not in {'MESH','EMPTY'}:continue
        corners=[o.matrix_world@Vector(v) for o in descendants(obj) if o.type=='MESH' for v in o.bound_box]
        bounds = {}
        if corners:
            low=[min(v[i] for v in corners) for i in range(3)]
            high=[max(v[i] for v in corners) for i in range(3)]
            bounds={'world_bounds_min':[round(v,4) for v in low],
                    'world_bounds_max':[round(v,4) for v in high],
                    'world_center':[round((low[i]+high[i])/2,4) for i in range(3)]}
        entries.append({'name':obj.name,'type':obj.type,'location':[round(v,4) for v in obj.location],
                        'rotation':[round(math.degrees(v),2) for v in obj.rotation_euler],
                        'dimensions':[round(v,4) for v in obj.dimensions],
                        'primitive':obj.get('studio_primitive','unknown'),
                        'top_scale':list(obj.get('studio_top_scale',[])),
                        'world_axis_z':[round(v,6) for v in (obj.matrix_world.to_3x3()@Vector((0,0,1))).normalized()],
                        'bevel_width':round(max([m.width for m in obj.modifiers if m.type=='BEVEL' and m.show_render] or [0]),4),
                        **bounds})
    if len(entries)>200:raise ValueError('Cena excede 200 objetos editáveis. Simplifique antes de importar.')
    return {'objects':entries,'triangles':triangles}


def main():
    request=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
    output=Path(request['output']);output.mkdir(parents=True,exist_ok=True)
    if request.get('base'):
        bpy.ops.wm.open_mainfile(filepath=request['base'],load_ui=False,use_scripts=False)
        normalize_names()
    else:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for action in request['actions']:apply(action)
    cam,center,size=frame_scene()
    scene_report=report()
    for label,offset in [('front',(0,-3,0)),('side',(3,0,0)),('perspective',(2,-3,1.8))]:
        cam.location=center+Vector(offset)*size
        cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
        bpy.context.scene.render.filepath=str(output/(label+'.png'))
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'model.blend'))
    (output/'scene.json').write_text(json.dumps(scene_report,indent=2),encoding='utf-8')

if __name__=='__main__':main()
