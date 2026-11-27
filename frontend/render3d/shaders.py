"""GLSL 330 shader sources for the 3D fight renderer."""

LIGHTING_UNIFORMS = """
uniform vec3 u_cam_pos;
uniform vec3 u_key_dir;
uniform vec3 u_key_col;
uniform vec3 u_fill_dir;
uniform vec3 u_fill_col;
uniform vec3 u_rim_dir;
uniform vec3 u_rim_col;
uniform vec3 u_sky;
uniform vec3 u_ground;
uniform vec3 u_fog_col;
uniform vec2 u_fog;          // near, far
uniform vec4 u_point_pos[4]; // xyz, radius
uniform vec4 u_point_col[4]; // rgb, intensity
uniform mat4 u_shadow_mat;
uniform sampler2DShadow u_shadow;
uniform float u_shadow_texel;
uniform float u_dim;          // 0..1 super-freeze darkening of the environment

float shadow_at(vec3 p, vec3 n) {
    vec4 sc = u_shadow_mat * vec4(p + n * 0.025, 1.0);
    vec3 c = sc.xyz / sc.w;
    if (c.x < 0.0 || c.x > 1.0 || c.y < 0.0 || c.y > 1.0 || c.z > 1.0) return 1.0;
    float bias = 0.0015;
    float t = u_shadow_texel * 1.4;
    float s = 0.0;
    s += texture(u_shadow, vec3(c.xy + vec2(-0.94, -0.40) * t, c.z - bias));
    s += texture(u_shadow, vec3(c.xy + vec2( 0.95, -0.77) * t, c.z - bias));
    s += texture(u_shadow, vec3(c.xy + vec2(-0.09, -0.93) * t, c.z - bias));
    s += texture(u_shadow, vec3(c.xy + vec2( 0.34,  0.29) * t, c.z - bias));
    s += texture(u_shadow, vec3(c.xy + vec2(-0.82,  0.54) * t, c.z - bias));
    s += texture(u_shadow, vec3(c.xy + vec2( 0.53,  0.91) * t, c.z - bias));
    return s / 6.0;
}

vec3 point_lights(vec3 p, vec3 n) {
    vec3 acc = vec3(0.0);
    for (int i = 0; i < 4; i++) {
        vec3 d = u_point_pos[i].xyz - p;
        float dist = length(d);
        float r = u_point_pos[i].w;
        if (r <= 0.0) continue;
        float att = clamp(1.0 - dist / r, 0.0, 1.0);
        att *= att;
        float ndl = max(dot(n, d / max(dist, 1e-4)), 0.0) * 0.8 + 0.2;
        acc += u_point_col[i].rgb * u_point_col[i].a * att * ndl;
    }
    return acc;
}
"""

# ---------------------------------------------------------------------------
# Skinned characters / static props (same vertex layout)
# ---------------------------------------------------------------------------
CHAR_VS = """
#version 330
uniform mat4 u_viewproj;
uniform mat4 u_bones[48];
in vec3 in_pos;
in vec3 in_nrm;
in vec3 in_col;
in vec4 in_mat;
in float in_bone;
out vec3 v_pos;
out vec3 v_nrm;
out vec3 v_col;
out vec4 v_mat;
void main() {
    mat4 b = u_bones[int(in_bone + 0.5)];
    vec4 wp = b * vec4(in_pos, 1.0);
    v_pos = wp.xyz;
    v_nrm = mat3(b) * in_nrm;
    v_col = in_col;
    v_mat = in_mat;
    gl_Position = u_viewproj * wp;
}
"""

CHAR_FS = """
#version 330
""" + LIGHTING_UNIFORMS + """
uniform float u_glow;       // accent emissive boost
uniform vec3 u_glow_col;
uniform float u_flash;      // hit flash 0..1
uniform vec3 u_flash_col;
uniform float u_rim_boost;
uniform float u_reflect;    // 1 when drawing the floor reflection
in vec3 v_pos;
in vec3 v_nrm;
in vec3 v_col;
in vec4 v_mat;
out vec4 f_color;
void main() {
    if (u_reflect > 0.5 && v_pos.y > 0.02) discard;
    vec3 N = normalize(v_nrm);
    vec3 V = normalize(u_cam_pos - v_pos);
    float rough = v_mat.x;
    float metal = v_mat.y;
    vec3 albedo = v_col * mix(0.72, 1.0, smoothstep(0.0, 0.7, v_pos.y));

    float sh = shadow_at(v_pos, N);
    float ndl = dot(N, u_key_dir);
    // stylised two-tone ramp with a soft terminator
    float hl = ndl * 0.5 + 0.5;
    float ramp = smoothstep(0.44, 0.56, hl) * mix(0.25, 1.0, sh);
    ramp = max(ramp, 0.0);
    vec3 key = u_key_col * mix(0.1, 1.0, ramp);
    float fndl = max(dot(N, u_fill_dir), 0.0);
    vec3 fill = u_fill_col * (fndl * 0.8 + 0.2);
    vec3 hemi = mix(u_ground, u_sky, N.y * 0.5 + 0.5) * 0.85;
    vec3 diffuse = albedo * (key + fill + hemi + point_lights(v_pos, N)) * (1.0 - metal * 0.75);

    // specular (Blinn-Phong, roughness driven) + fake environment for metals
    vec3 H = normalize(u_key_dir + V);
    float shin = mix(140.0, 10.0, rough);
    float spec = pow(max(dot(N, H), 0.0), shin) * (1.0 - rough) * 2.2 * mix(0.3, 1.0, sh);
    spec = smoothstep(0.08, 0.5, spec) * 1.4 + spec * 0.3;
    vec3 spec_col = mix(vec3(0.6), albedo * 1.6, metal);
    vec3 R = reflect(-V, N);
    vec3 env = mix(u_ground * 1.3, u_sky * 1.6 + vec3(0.18), smoothstep(-0.3, 0.6, R.y));
    vec3 specular = spec_col * spec * u_key_col * 0.6 + env * albedo * metal * 0.85;

    // rim light (strong, coloured) - sells the 3D silhouette
    float ndv = max(dot(N, V), 0.0);
    float fres = pow(1.0 - ndv, 3.0);
    float rim_mask = smoothstep(-0.25, 0.6, dot(N, u_rim_dir));
    vec3 rim = u_rim_col * fres * rim_mask * (1.3 + u_rim_boost);

    vec3 emissive = albedo * (v_mat.z + v_mat.w * u_glow) + u_glow_col * u_glow * fres * 0.8;
    vec3 col = (diffuse + specular) * (1.0 - u_dim * 0.7) + rim + emissive;
    col = mix(col, u_flash_col * 2.4, u_flash);
    float dist = length(u_cam_pos - v_pos);
    float fog = clamp((dist - u_fog.x) / max(u_fog.y - u_fog.x, 1e-3), 0.0, 1.0) * 0.6;
    col = mix(col, u_fog_col, fog);
    f_color = vec4(col, 1.0);
}
"""

# Afterimage / ghost: additive fresnel silhouette in a flat colour
GHOST_FS = """
#version 330
uniform vec3 u_cam_pos;
uniform vec3 u_ghost_col;
uniform float u_ghost_alpha;
in vec3 v_pos;
in vec3 v_nrm;
in vec3 v_col;
in vec4 v_mat;
out vec4 f_color;
void main() {
    vec3 N = normalize(v_nrm);
    vec3 V = normalize(u_cam_pos - v_pos);
    float fres = pow(1.0 - max(dot(N, V), 0.0), 1.6);
    f_color = vec4(u_ghost_col * (0.25 + fres * 1.6) * u_ghost_alpha, 1.0);
}
"""

DEPTH_VS = """
#version 330
uniform mat4 u_viewproj;
uniform mat4 u_bones[48];
in vec3 in_pos;
in float in_bone;
void main() {
    gl_Position = u_viewproj * (u_bones[int(in_bone + 0.5)] * vec4(in_pos, 1.0));
}
"""

DEPTH_FS = """
#version 330
void main() { }
"""

# ---------------------------------------------------------------------------
# Floor: procedural material per arena + shadows + reflection blend
# ---------------------------------------------------------------------------
FLOOR_VS = """
#version 330
uniform mat4 u_viewproj;
in vec3 in_pos;
out vec3 v_pos;
void main() {
    v_pos = in_pos;
    gl_Position = u_viewproj * vec4(in_pos, 1.0);
}
"""

FLOOR_FS = """
#version 330
""" + LIGHTING_UNIFORMS + """
uniform int u_floor_type;
uniform vec3 u_floor_a;
uniform vec3 u_floor_b;
uniform vec3 u_floor_line;
uniform vec3 u_floor_emit;
uniform float u_gloss;
uniform float u_time;
uniform float u_wall;      // arena half width (m)
uniform vec2 u_blob[2];    // contact shadow centres (x, z)
uniform vec2 u_blob_r;     // contact radii (scaled by height)
in vec3 v_pos;
out vec4 f_color;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
    float s = 0.0, a = 0.5;
    for (int i = 0; i < 4; i++) { s += vnoise(p) * a; p *= 2.03; a *= 0.5; }
    return s;
}

void main() {
    vec2 p = v_pos.xz;
    vec3 base;
    float gloss = u_gloss;
    float line = 0.0;
    vec3 emit = vec3(0.0);
    float n = fbm(p * 1.3);
    if (u_floor_type == 0) {            // stone tiles
        vec2 t = p / vec2(1.2, 0.9);
        vec2 id = floor(t);
        vec2 f = fract(t);
        float edge = min(min(f.x, 1.0 - f.x) * 1.2, min(f.y, 1.0 - f.y) * 0.9);
        line = 1.0 - smoothstep(0.0, 0.035, edge);
        base = mix(u_floor_a, u_floor_b, hash(id) * 0.6 + n * 0.5);
        gloss *= 0.7 + 0.6 * vnoise(p * 3.0);
    } else if (u_floor_type == 1) {     // wet concrete with puddles
        base = mix(u_floor_a, u_floor_b, n);
        float puddle = smoothstep(0.52, 0.6, fbm(p * 0.45 + 3.0));
        gloss = mix(u_gloss * 0.45, 1.0, puddle);
        base *= mix(1.0, 0.55, puddle);
        vec2 t = p / 2.5;
        vec2 f = fract(t);
        line = (1.0 - smoothstep(0.0, 0.01, min(f.x, f.y))) * 0.5;
    } else if (u_floor_type == 2) {     // riveted metal plates
        vec2 t = p / vec2(1.6, 1.0);
        vec2 id = floor(t);
        vec2 f = fract(t);
        float edge = min(min(f.x, 1.0 - f.x) * 1.6, min(f.y, 1.0 - f.y));
        line = 1.0 - smoothstep(0.0, 0.03, edge);
        vec2 rv = abs(f - vec2(0.06)) ;
        float rivet = 1.0 - smoothstep(0.015, 0.03, length((fract(t * 2.0) - 0.08) * vec2(1.6, 1.0)));
        base = mix(u_floor_a, u_floor_b, hash(id) * 0.5 + n * 0.6) + rivet * 0.06;
        gloss *= 0.6 + 0.8 * n;
    } else if (u_floor_type == 3) {     // obsidian with glowing lava cracks
        base = mix(u_floor_a, u_floor_b, n);
        float c = abs(fbm(p * 0.9) - 0.5);
        float crack = 1.0 - smoothstep(0.0, 0.03, c);
        float pulse = 0.75 + 0.25 * sin(u_time * 2.0 + p.x * 0.7);
        emit = u_floor_emit * crack * pulse;
        base *= 1.0 - crack * 0.6;
    } else if (u_floor_type == 4) {     // wooden planks
        float plank = floor(p.y / 0.32);
        float px = p.x + hash(vec2(plank, 2.0)) * 3.0;
        float f = fract(p.y / 0.32);
        line = 1.0 - smoothstep(0.0, 0.05, min(f, 1.0 - f));
        float grain = vnoise(vec2(px * 1.5, p.y * 30.0));
        base = mix(u_floor_a, u_floor_b, grain * 0.7 + hash(vec2(plank, 7.0)) * 0.4);
        float seam = fract(px / 2.4);
        line = max(line, 1.0 - smoothstep(0.0, 0.006, min(seam, 1.0 - seam)));
    } else if (u_floor_type == 5) {     // packed snow / ice
        float ice = smoothstep(0.45, 0.65, fbm(p * 0.35 + 7.0));
        base = mix(u_floor_a, u_floor_b, ice) * (0.9 + 0.2 * vnoise(p * 6.0));
        gloss = mix(u_gloss * 0.25, u_gloss, ice);
    } else {                            // marble arena with gold inlay ring
        float veins = smoothstep(0.0, 0.08, abs(fbm(p * 0.8 + vec2(fbm(p * 1.7))) - 0.5));
        base = mix(u_floor_line * 0.9, mix(u_floor_a, u_floor_b, n), veins);
        float ring = abs(length(p * vec2(0.45, 1.0)) - 2.6);
        line = 1.0 - smoothstep(0.02, 0.05, ring);
    }
    base = mix(base, u_floor_line, line * 0.85);
    gloss *= (1.0 - line * 0.8);

    vec3 N = vec3(0.0, 1.0, 0.0);
    vec3 V = normalize(u_cam_pos - v_pos);
    float sh = shadow_at(v_pos, N);
    // soft contact shadows under the feet (always on, even beyond the shadow map)
    float contact = 1.0;
    for (int i = 0; i < 2; i++) {
        vec2 d = (p - u_blob[i]) / vec2(u_blob_r[i], u_blob_r[i] * 0.55);
        contact *= mix(1.0, 0.45, exp(-dot(d, d) * 2.2));
    }
    float ndl = max(dot(N, u_key_dir), 0.0);
    vec3 light = u_key_col * ndl * mix(0.35, 1.0, sh) + mix(u_ground, u_sky, 0.8) + u_fill_col * 0.3
                 + point_lights(v_pos, N);
    vec3 col = base * light * contact * (1.0 - u_dim * 0.55);
    vec3 H = normalize(u_key_dir + V);
    col += u_key_col * pow(max(dot(N, H), 0.0), 60.0) * gloss * 0.5 * sh;
    col += emit;

    // beyond the walls the floor darkens slightly (ring-out area)
    float outside = smoothstep(u_wall, u_wall + 0.5, abs(v_pos.x));
    col *= 1.0 - outside * 0.25;

    float dist = length(u_cam_pos - v_pos);
    float fog = clamp((dist - u_fog.x) / max(u_fog.y - u_fog.x, 1e-3), 0.0, 1.0);
    col = mix(col, u_fog_col * (1.0 - u_dim * 0.6), fog);
    // reflection shows through on glossy parts (fresnel)
    float fres = 0.25 + 0.75 * pow(1.0 - max(V.y, 0.0), 4.0);
    float refl = clamp(gloss * fres, 0.0, 0.85) * (1.0 - fog);
    float far_fade = 1.0 - smoothstep(u_fog.x * 0.9, u_fog.x * 1.45, dist);
    f_color = vec4(col, (1.0 - refl) * far_fade);
}
"""

# ---------------------------------------------------------------------------
# Backdrop: the arena painting on a distant curved plane
# ---------------------------------------------------------------------------
BACKDROP_VS = """
#version 330
uniform mat4 u_viewproj;
in vec3 in_pos;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = u_viewproj * vec4(in_pos, 1.0);
}
"""

BACKDROP_FS = """
#version 330
uniform sampler2D u_tex;
uniform float u_exposure;
uniform vec3 u_fog_col;
uniform float u_haze;
uniform float u_dim;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec3 c = texture(u_tex, v_uv).rgb;
    c = pow(c, vec3(2.2)) * u_exposure;
    // depth haze towards the bottom (where it meets the floor)
    float h = smoothstep(0.55, 0.25, v_uv.y) * u_haze;
    c = mix(c, u_fog_col, h);
    c *= 1.0 - u_dim * 0.75;
    f_color = vec4(c, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Billboard particles (instanced)
# ---------------------------------------------------------------------------
PARTICLE_VS = """
#version 330
uniform mat4 u_view;
uniform mat4 u_proj;
in vec2 in_corner;
in vec3 i_pos;
in vec3 i_vel;
in vec4 i_col;
in vec2 i_size_kind;
out vec2 v_uv;
out vec4 v_col;
flat out int v_kind;
void main() {
    float size = i_size_kind.x;
    int kind = int(i_size_kind.y + 0.5);
    vec4 vp = u_view * vec4(i_pos, 1.0);
    vec2 offs;
    if (kind == 1) {
        vec3 vv = (u_view * vec4(i_vel, 0.0)).xyz;
        vec2 d = vv.xy;
        float l = length(d);
        vec2 ax = l > 1e-5 ? d / l : vec2(1.0, 0.0);
        vec2 ay = vec2(-ax.y, ax.x);
        float len = size * (1.0 + l * 0.09);
        offs = ax * in_corner.x * len + ay * in_corner.y * size * 0.35;
    } else if (kind == 5) {
        // ground-aligned ring (lies on the floor)
        vec4 wp = vec4(i_pos + vec3(in_corner.x, 0.0, in_corner.y) * size, 1.0);
        vp = u_view * wp;
        offs = vec2(0.0);
    } else {
        offs = in_corner * size;
    }
    vp.xy += offs;
    v_uv = in_corner;
    v_col = i_col;
    v_kind = kind;
    gl_Position = u_proj * vp;
}
"""

PARTICLE_FS = """
#version 330
in vec2 v_uv;
in vec4 v_col;
flat in int v_kind;
out vec4 f_color;
void main() {
    float r = length(v_uv);
    float a;
    if (v_kind == 0) {              // soft glow dot
        a = exp(-r * r * 5.0);
    } else if (v_kind == 1) {       // streak spark
        a = exp(-(v_uv.x * v_uv.x) * 2.5 - (v_uv.y * v_uv.y) * 7.0);
    } else if (v_kind == 2 || v_kind == 5) {  // shock ring
        a = exp(-pow((r - 0.78) * 9.0, 2.0)) + exp(-r * r * 6.0) * 0.12;
    } else if (v_kind == 3) {       // smoke / dust (alpha blended pass)
        a = smoothstep(1.0, 0.0, r);
        a = a * a;
    } else if (v_kind == 4) {       // star flash
        float cross = exp(-abs(v_uv.x) * 18.0) + exp(-abs(v_uv.y) * 18.0);
        a = exp(-r * r * 7.0) + cross * (1.0 - r) * 0.8;
    } else {                        // 6: radial speed line
        a = exp(-(v_uv.y * v_uv.y) * 40.0) * (1.0 - abs(v_uv.x));
    }
    if (r > 1.0 && v_kind != 1 && v_kind != 6) a = 0.0;
    if (v_kind == 3) {
        f_color = vec4(v_col.rgb, v_col.a * a);
    } else {
        f_color = vec4(v_col.rgb * v_col.a * a, 1.0);
    }
}
"""

# Ribbon trails (additive)
RIBBON_VS = """
#version 330
uniform mat4 u_viewproj;
in vec3 in_pos;
in vec4 in_col;
out vec4 v_col;
void main() {
    v_col = in_col;
    gl_Position = u_viewproj * vec4(in_pos, 1.0);
}
"""

RIBBON_FS = """
#version 330
in vec4 v_col;
out vec4 f_color;
void main() {
    f_color = vec4(v_col.rgb * v_col.a, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------
QUAD_VS = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

BRIGHT_FS = """
#version 330
uniform sampler2D u_tex;
uniform vec2 u_texel;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec3 c = texture(u_tex, v_uv + u_texel * vec2(-1, -1)).rgb
           + texture(u_tex, v_uv + u_texel * vec2( 1, -1)).rgb
           + texture(u_tex, v_uv + u_texel * vec2(-1,  1)).rgb
           + texture(u_tex, v_uv + u_texel * vec2( 1,  1)).rgb;
    c *= 0.25;
    float l = max(max(c.r, c.g), c.b);
    float k = clamp((l - 1.4) / 2.0, 0.0, 1.0);
    f_color = vec4(c * k * k, 1.0);
}
"""

BLUR_FS = """
#version 330
uniform sampler2D u_tex;
uniform vec2 u_dir;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec3 c = texture(u_tex, v_uv).rgb * 0.227;
    c += texture(u_tex, v_uv + u_dir * 1.385).rgb * 0.316;
    c += texture(u_tex, v_uv - u_dir * 1.385).rgb * 0.316;
    c += texture(u_tex, v_uv + u_dir * 3.231).rgb * 0.070;
    c += texture(u_tex, v_uv - u_dir * 3.231).rgb * 0.070;
    f_color = vec4(c, 1.0);
}
"""

COMPOSITE_FS = """
#version 330
uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform float u_bloom_amt;
uniform vec3 u_grade;
uniform float u_grade_amt;
uniform float u_exposure;
uniform float u_vignette;
uniform vec2 u_streak_center;   // super freeze speed lines (uv)
uniform float u_streak;
uniform float u_time;
uniform float u_flash;          // full-screen flash
in vec2 v_uv;
out vec4 f_color;

vec3 aces(vec3 x) {
    const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}
float hash(float n) { return fract(sin(n) * 43758.5453); }

void main() {
    vec2 uv = vec2(v_uv.x, 1.0 - v_uv.y);   // flip: pygame surfaces are top-down
    vec3 c = texture(u_scene, uv).rgb;
    c += texture(u_bloom, uv).rgb * u_bloom_amt;
    if (u_streak > 0.0) {
        vec2 d = (uv - u_streak_center) * vec2(1.7, 1.0);
        float ang = atan(d.y, d.x);
        float seg = floor(ang * 40.0);
        float lines = step(0.55, hash(seg + floor(u_time * 20.0))) * smoothstep(0.15, 0.75, length(d));
        c = mix(c, vec3(1.6, 1.4, 1.0), lines * u_streak * 0.22);
    }
    c *= u_exposure;
    c = aces(c);
    c = pow(c, vec3(1.0 / 2.2));
    c = mix(c, c * u_grade, u_grade_amt);
    vec2 q = v_uv - 0.5;
    c *= 1.0 - dot(q, q) * u_vignette;
    c = mix(c, vec3(1.0), u_flash);
    f_color = vec4(c, 1.0);
}
"""
