import bpy
import os
from pathlib import Path
from mathutils import Vector
A=Path(os.environ['DEBUGYCH_ASSET_WORKSPACE']);O=Path(os.environ.get('DEBUGYCH_COMPANION_OUTPUT',str(Path(__file__).resolve().parents[2]/'apps/web/public/companion')));bpy.ops.wm.open_mainfile(filepath=str(A/'outputs/assets/debugych/typing_v2_1/debugych_fixing_typing.blend'));s=bpy.context.scene;r=bpy.data.objects['Debugych_Rig'];r.animation_data.action=bpy.data.actions['idle'];s.frame_set(0)
for o in s.objects:
 if o.type=='MESH':o.hide_render=not any(m.type=='ARMATURE'and m.object==r for m in o.modifiers)
s.camera.location=(1.15,-2.7,1.18);s.camera.rotation_euler=(Vector((0,0,.8))-s.camera.location).to_track_quat('-Z','Y').to_euler();s.camera.data.type='ORTHO';s.camera.data.ortho_scale=1.15;s.render.engine='CYCLES';s.cycles.samples=12;s.cycles.use_denoising=True;s.render.film_transparent=True;s.render.resolution_x=360;s.render.resolution_y=480;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGBA';s.render.filepath=str(O/'static.png');bpy.ops.render.render(write_still=True);print('STATIC_READY')
