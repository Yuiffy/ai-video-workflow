"""Import the user's PMX once and retain a clean, packed Blender source."""
import json
from pathlib import Path
import bpy
import addon_utils
from mathutils import Vector

OUT = Path(__file__).resolve().parents[2] / 'outputs/sui-frisbee-3d'
MODEL = Path('F:/fworkspace/workspace3d/Suifel_yora/Suifel.pmx')
addon_utils.enable('bl_ext.user_default.mmd_tools', default_set=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mmd_tools.import_model(filepath=str(MODEL), scale=.08,
    types={'MESH', 'ARMATURE', 'MORPHS'}, rename_bones=False, log_level='WARNING')
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
info = {
 'armature': arm.name,
 'objects': [{'name': o.name, 'type': o.type, 'parent': o.parent.name if o.parent else None,
              'dimensions': list(o.dimensions)} for o in bpy.context.scene.objects],
 'bones': [{'name': b.name, 'head': list(b.head_local), 'tail': list(b.tail_local),
            'parent': b.parent.name if b.parent else None} for b in arm.data.bones],
 'meshes': [{'name': o.name, 'vertices': len(o.data.vertices),
             'shapes': list(o.data.shape_keys.key_blocks.keys()) if o.data.shape_keys else [],
             'materials': [m.name if m else '' for m in o.data.materials]} for o in meshes],
 'materials': [{'name': m.name, 'images': [{'node': n.name, 'image': n.image.name,
                 'file': n.image.filepath} for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image]}
               for m in bpy.data.materials if m.use_nodes],
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'model-inspection.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
for image in bpy.data.images:
    if image.source == 'FILE' and image.has_data:
        image.pack()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'suifel-imported.blend'), compress=True)

points = [o.matrix_world @ Vector(v) for o in meshes for v in o.bound_box]
lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
print('MODEL_BOUNDS', list(lo), list(hi))
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.eevee.taa_render_samples = 32
scene.render.resolution_x = 720
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.world.color = (.35, .35, .35)
scene.view_settings.view_transform = 'Standard'
bpy.ops.object.camera_add(location=(0, -5, 1.3))
cam = bpy.context.object
target = (lo + hi) / 2
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.type = 'ORTHO'
cam.data.ortho_scale = (hi.z - lo.z) * 1.25
scene.camera = cam
for loc, energy, size in [((2,-3,4),500,5),((-3,-1,2),220,4),((0,3,4),400,3)]:
    bpy.ops.object.light_add(type='AREA', location=loc)
    light = bpy.context.object
    light.data.energy = energy
    light.data.shape = 'DISK'
    light.data.size = size
    light.rotation_euler = (target - light.location).to_track_quat('-Z','Y').to_euler()
scene.render.filepath = str(OUT / 'previews/imported.png')
bpy.ops.render.render(write_still=True)
