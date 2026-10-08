// Lights the room. The script hands over five pictures of the same frame:
// albedo (what things are made of), the carve mask (R cut through, G etched
// or cut, B rind), the same mask at quarter size, the ghost, and what shines
// on its own. Here they meet the moon and the candle inside the pumpkin.

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

struct U {
    res: vec2<f32>,
    flamePos: vec2<f32>, // pixels
    center: vec2<f32>,   // pumpkin centre, pixels
    radii: vec2<f32>,    // pumpkin radii, pixels
    time: f32,
    lit: f32,      // 0 moonlight .. 1 candlelight (room)
    flame: f32,    // candle brightness with flicker, gust and slider
    haze: f32,     // 0..1
    scale: f32,    // design units to pixels
    lean: f32,     // -1..1, the flame bends
    phantom: f32,  // 0..1
    gust: f32,     // 0..1
    open: f32,     // how much of the face is open, 0..1
    flameSize: f32,// the flame's own size (strike overshoot)
    slide: f32,   // 0..1, a gust slides the face out of the light
    pad1: f32,
};

@group(0) @binding(0) var<uniform> u: U;
@group(0) @binding(1) var albedoTex: texture_2d<f32>;
@group(0) @binding(2) var maskTex: texture_2d<f32>;
@group(0) @binding(3) var maskLoTex: texture_2d<f32>;
@group(0) @binding(4) var ghostTex: texture_2d<f32>; // the wall: R carving, G dark, B the face alive
@group(0) @binding(5) var emitTex: texture_2d<f32>;
@group(0) @binding(6) var samp: sampler;

@vertex
fn vs_main(@builtin(vertex_index) idx: u32) -> VertexOutput {
    var pos = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
    let p = pos[idx];
    var out: VertexOutput;
    out.position = vec4<f32>(p, 0.0, 1.0);
    out.uv = vec2<f32>(p.x * 0.5 + 0.5, 0.5 - p.y * 0.5);
    return out;
}

fn hash2(p: vec2<f32>) -> f32 {
    let h = dot(p, vec2<f32>(127.1, 311.7));
    return fract(sin(h) * 43758.5453);
}

fn noise(p: vec2<f32>) -> f32 {
    let i = floor(p);
    let f = fract(p);
    let a = hash2(i);
    let b = hash2(i + vec2<f32>(1.0, 0.0));
    let c = hash2(i + vec2<f32>(0.0, 1.0));
    let d = hash2(i + vec2<f32>(1.0, 1.0));
    let w = f * f * (3.0 - 2.0 * f);
    return mix(mix(a, b, w.x), mix(c, d, w.x), w.y);
}

fn fbm(p0: vec2<f32>) -> f32 {
    var p = p0;
    var v = 0.0;
    var a = 0.5;
    for (var i = 0; i < 5; i = i + 1) {
        v = v + a * noise(p);
        p = p * 2.03 + vec2<f32>(17.0, 9.0);
        a = a * 0.5;
    }
    return v;
}

// light through the carving: cut lets everything out, etched skin some
fn leak(m: vec4<f32>) -> f32 {
    return m.r + 0.28 * max(m.g - m.r, 0.0);
}

// the soft glow of the quarter-size mask: two rings of taps, rotated per
// pixel so the taps never line up into stepped copies of the cut
fn glow(uv: vec2<f32>, radius: f32, rot: f32) -> f32 {
    var acc = leak(textureSample(maskLoTex, samp, uv)) * 2.0;
    let px = radius / u.res;
    for (var i = 0; i < 10; i = i + 1) {
        let a = f32(i) * 0.6283 + rot;
        let r = select(1.0, 0.5, (i & 1) == 1);
        acc = acc + leak(textureSample(maskLoTex, samp, uv + vec2<f32>(cos(a), sin(a)) * px * r));
    }
    return acc / 12.0;
}

// a candle flame, seen through the holes: a teardrop whose tip bends with the lean
fn flameShape(p: vec2<f32>, s: f32) -> f32 {
    let q = (p - u.flamePos) / (s * max(u.flameSize, 0.01));
    // 0 at the wick, 1 at the tip (the flame rises 48 units)
    let h = clamp(-q.y / 48.0, 0.0, 1.0);
    let x = q.x - u.lean * 14.0 * h * h;
    let width = 9.0 * sqrt(max(1.0 - h, 0.0)) * (0.55 + 0.45 * smoothstep(0.0, 0.25, h));
    let inside = 1.0 - smoothstep(width * 0.55, width + 0.5, abs(x));
    let span = smoothstep(-4.0, 2.0, -q.y) * (1.0 - smoothstep(46.0, 50.0, -q.y));
    return inside * span;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let t = u.time;
    let uv = in.uv;
    let px = uv * u.res;
    let s = u.scale;

    let alb = textureSample(albedoTex, samp, uv).rgb;
    let m = textureSample(maskTex, samp, uv);
    let em = textureSample(emitTex, samp, uv).rgb;
    let cut = m.r;
    let etch = clamp(m.g - m.r, 0.0, 1.0);
    let body = m.b;
    let L = u.lit;
    let F = u.flame;

    // where we are relative to the pumpkin
    let rel = (px - u.center) / u.radii;
    let fromFlame = px - u.flamePos;
    let dFlame = length(fromFlame) / s;

    // moonlight from the window at the left, colder and dimmer once the candle is the light
    let moonCol = vec3<f32>(0.30, 0.36, 0.55);
    let beam = smoothstep(0.0, 1.0, 1.0 - abs((px.x / s - 160.0) * 0.6 + (px.y / s - 420.0) * 0.55 - 120.0) / 420.0);
    var ambient = moonCol * (0.55 + 0.35 * beam) * mix(1.0, 0.38, L) + vec3<f32>(0.02, 0.02, 0.03);

    // warm light from the open face onto the room
    let warm = vec3<f32>(1.0, 0.56, 0.20);
    let spillFall = 1.0 / (1.0 + pow(dFlame / 300.0, 2.0));
    let spill = F * (0.08 + 0.5 * u.open) * spillFall * 0.55;
    // the table catches most of it, in front of the pumpkin
    let onTable = smoothstep(600.0, 640.0, px.y / s);
    let pool = F * (0.2 + u.open) * exp(-pow((px.x - u.flamePos.x) / (s * 260.0), 2.0) - pow((px.y / s - 690.0) / 70.0, 2.0)) * onTable;

    var col = alb * (ambient + warm * (spill * (1.0 - body) + pool * 0.9));

    // the rind: lit from inside near every cut, glowing through thin skin
    let rot = hash2(floor(px)) * 6.2832;
    let near = glow(uv, 9.0 * s, rot);
    let wide = glow(uv, 26.0 * s, rot + 1.7);
    let sss = (near * 1.3 + wide * 0.7) * F;
    col = col + body * (1.0 - cut) * vec3<f32>(1.0, 0.36, 0.05) * sss * 0.62;
    // the whole pumpkin warms a little from within
    let inner = 1.0 - smoothstep(0.2, 1.05, length(rel * vec2<f32>(1.0, 1.1)));
    col = col + body * (1.0 - cut) * vec3<f32>(0.62, 0.2, 0.03) * inner * F * 0.36 + body * (1.0 - cut) * vec3<f32>(0.3, 0.09, 0.015) * F * 0.3;

    // etched skin: paler flesh in the moon, glowing amber once lit
    // shaved flesh is cream-yellow (#E9C27A) in the moon, and glows once lit
    let flesh = vec3<f32>(0.91, 0.76, 0.48);
    // thin flesh: cream-yellow in the moon; once lit it glows amber, as bright as the flame allows
    let etchCol = flesh * (0.22 + 0.25 * beam) * (1.0 - L) + vec3<f32>(0.03, 0.035, 0.05) * (1.0 - L)
        + vec3<f32>(1.0, 0.48, 0.10) * F * (0.85 + 0.6 * near);
    col = mix(col, etchCol, etch * body);

    // through the holes: the inside of the pumpkin, the candle, the flame
    let outward = normalize(px - u.center + vec2<f32>(0.001, 0.001));
    let thick = 7.0 * s;
    let behind = textureSample(maskTex, samp, uv + outward * thick / u.res).r;
    let rim = cut * (1.0 - behind);
    let wallFall = exp(-dFlame / 170.0);
    var interior = vec3<f32>(0.035, 0.014, 0.006) + vec3<f32>(0.04, 0.05, 0.08) * (1.0 - L) * 0.4;
    // the back wall: hot gold close to the flame, deep red-orange towards the rim,
    // with the inner ribs of the pumpkin showing as soft vertical bands
    let ribs = 0.86 + 0.14 * cos(rel.x * 15.7 + 0.6) * (1.0 - abs(rel.x) * 0.5);
    let fibre = 0.94 + 0.12 * fbm(vec2<f32>(px.x / (s * 9.0), px.y / (s * 40.0)));
    // the brightest thing in the room: the lit back wall, falling off from the flame
    let wallHot = mix(vec3<f32>(0.9, 0.45, 0.12), vec3<f32>(1.0, 0.82, 0.5), wallFall);
    interior = interior + wallHot * F * (1.4 + 2.2 * wallFall) * ribs * fibre;
    // inside the lid it stays darker
    interior = interior * (1.0 - 0.45 * smoothstep(-0.2, -0.75, rel.y) * (1.0 - wallFall));
    // the candle: a stub of wax under the flame, lit from the top, rounder at the sides
    let cdx = (px.x - u.flamePos.x) / s;
    let cdy = (px.y - u.flamePos.y) / s;
    let cw = 13.0;
    let side = clamp(abs(cdx) / cw, 0.0, 1.0);
    let cyl = sqrt(max(1.0 - side * side, 0.0));
    let topY = 7.0 + 3.0 * sqrt(max(1.0 - side * side, 0.0));
    let waxIn = (1.0 - smoothstep(cw - 0.8, cw + 0.4, abs(cdx))) * smoothstep(topY - 1.2, topY + 0.3, cdy);
    let waxLight = (0.05 + F * (0.42 + 1.1 * exp(-max(cdy - topY, 0.0) / 40.0))) * (0.45 + 0.55 * cyl + 0.25 * smoothstep(0.2, -0.6, cdx / cw));
    var waxCol = vec3<f32>(1.0, 0.74, 0.42) * waxLight;
    // a soft highlight down the left of the wax, and a drip running down the front
    let hl = exp(-pow((cdx / cw + 0.42) / 0.13, 2.0));
    waxCol = waxCol + vec3<f32>(1.0, 0.9, 0.72) * hl * (0.15 + 0.55 * F * exp(-max(cdy - topY, 0.0) / 50.0));
    let dripX = cdx - cw * 0.45;
    let dripLen = topY + 24.0;
    let drip = (1.0 - smoothstep(2.0, 3.0, abs(dripX))) * step(cdy, dripLen)
        + (1.0 - smoothstep(3.2, 4.2, length(vec2<f32>(dripX, cdy - dripLen))));
    waxCol = mix(waxCol, waxCol * 1.35 + vec3<f32>(0.10, 0.06, 0.02) * F, clamp(drip, 0.0, 1.0) * step(topY, cdy));
    // translucent glow at the top where the wax pools around the wick
    waxCol = waxCol + vec3<f32>(1.0, 0.55, 0.15) * F * exp(-max(cdy - topY, 0.0) / 5.0) * 0.8 * cyl;
    interior = mix(interior, waxCol, waxIn);
    // the wick
    let wick = (1.0 - smoothstep(0.7, 1.4, abs(cdx - u.lean * 1.5))) * smoothstep(-1.0, 0.0, cdy) * (1.0 - smoothstep(topY - 0.5, topY + 0.5, cdy));
    interior = mix(interior, vec3<f32>(0.08, 0.05, 0.04), wick);
    let fl = flameShape(px, s);
    let core = flameShape(px + vec2<f32>(0.0, -6.0 * s), s * 0.55);
    interior = interior + (vec3<f32>(1.0, 0.62, 0.18) * fl * 2.2 + vec3<f32>(1.0, 0.95, 0.8) * core * 2.0) * min(F * 1.4, 1.0) * step(0.02, u.flameSize);
    // the inner wall seen through the hole: flesh in shadow, darker than the light behind it
    let rimCol = vec3<f32>(0.62, 0.30, 0.09) * F * (0.55 + 0.6 * wallFall) + flesh * ambient * 0.35;
    let hole = mix(interior, rimCol, rim);
    col = mix(col, hole, cut);
    // and a thin pale band where the knife cut the rind
    let e = 2.4 * s / u.res;
    let edgeN = max(max(textureSample(maskTex, samp, uv + vec2<f32>(e.x, 0.0)).r, textureSample(maskTex, samp, uv - vec2<f32>(e.x, 0.0)).r),
                    max(textureSample(maskTex, samp, uv + vec2<f32>(0.0, e.y)).r, textureSample(maskTex, samp, uv - vec2<f32>(0.0, e.y)).r));
    let band = clamp(edgeN - cut, 0.0, 1.0) * body;
    let bandCol = flesh * (ambient * 0.9 + vec3<f32>(0.05)) * (1.0 - L) + vec3<f32>(1.0, 0.58, 0.22) * F * 1.2;
    col = mix(col, bandCol, band * mix(0.85, 0.55, L));
    // bloom: the bright holes spill 10-20 px of warm light onto the rind around them
    col = col + body * (1.0 - cut) * vec3<f32>(1.0, 0.62, 0.25) * (near * 1.1 + wide * 0.35) * F * 0.55;

    // moonlight catches the pumpkin's edge that faces the window
    let toWindow = normalize(vec2<f32>(-1.0, -0.55));
    let edge = body * (1.0 - textureSample(maskTex, samp, uv + toWindow * 7.0 * s / u.res).b);
    col = col + moonCol * edge * 0.3 * (1.0 - cut);

    // what shines on its own
    // what shines on its own: the window (never over the pumpkin) and the warm rim the candle puts on the stem
    col = col + em * max(1.0 - body, smoothstep(0.0, 0.05, em.r - em.b));

    // rays: march from this pixel toward the flame, collecting the light that leaks
    let steps = 36;
    var acc = 0.0;
    var w = 1.0;
    let toward = (u.flamePos / u.res - uv);
    let dlen = length(toward);
    let stepUv = toward / f32(steps) * 0.92;
    var sp = uv;
    // a little jitter hides the banding
    sp = sp + stepUv * hash2(px + fract(t) * 37.0);
    for (var i = 0; i < steps; i = i + 1) {
        sp = sp + stepUv;
        acc = acc + leak(textureSample(maskLoTex, samp, sp)) * w;
        w = w * 0.968;
    }
    var rays = acc / f32(steps);
    // only outside the pumpkin, thickest in haze
    let smoke = fbm(vec2<f32>(px.x / (s * 220.0) + t * 0.04, px.y / (s * 160.0) - t * 0.06));
    let hz = u.haze * (0.45 + 0.9 * smoke);
    rays = rays * (1.0 - body) * hz * F * (1.0 - u.gust * 0.6);
    col = col + warm * rays * 3.6;

    // the wall above the pumpkin: your carving thrown up by the candle, hard
    // edged with a small penumbra, and the face it becomes
    let glass = 1.0 - smoothstep(0.04, 0.12, dot(em, vec3<f32>(0.3, 0.5, 0.2)));
    let pe = 1.6 * s / u.res;
    var wt = textureSample(ghostTex, samp, uv) * 0.4;
    wt = wt + textureSample(ghostTex, samp, uv + vec2<f32>(cos(rot), sin(rot)) * pe) * 0.15;
    wt = wt + textureSample(ghostTex, samp, uv - vec2<f32>(cos(rot), sin(rot)) * pe) * 0.15;
    wt = wt + textureSample(ghostTex, samp, uv + vec2<f32>(-sin(rot), cos(rot)) * pe) * 0.15;
    wt = wt + textureSample(ghostTex, samp, uv - vec2<f32>(-sin(rot), cos(rot)) * pe) * 0.15;
    let ph = u.phantom;
    let Fw = min(F, 1.2);
    let dark = 1.0 - clamp(wt.g, 0.0, 1.0) * min(1.0, ph * 1.6);
    let litWall = Fw * (wt.r * (1.0 - ph * (1.0 - u.slide)) + wt.b * ph);
    let selfWall = ph * wt.b * (1.0 - min(Fw, 1.0)) * 0.9;
    let wallShape = clamp((litWall + selfWall) * dark, 0.0, 1.6);
    // never over the window and the moon (design units: the window is x 60..270, y 140..490)
    let dpx = px / s;
    let winBox = smoothstep(40.0, 70.0, dpx.x) * (1.0 - smoothstep(262.0, 292.0, dpx.x))
        * smoothstep(120.0, 150.0, dpx.y) * (1.0 - smoothstep(482.0, 512.0, dpx.y));
    let wallOn = (1.0 - body) * glass * (1.0 - 0.9 * winBox);
    // the room around it goes darker while it watches, so it stands out
    col = col * (1.0 - 0.28 * ph * wallOn);
    let wallCol = mix(vec3<f32>(1.0, 0.62, 0.26), vec3<f32>(0.86, 0.95, 0.62), 0.35 * ph * (1.0 - min(Fw, 1.0)) + 0.12 * ph);
    col = col + wallCol * wallShape * wallOn * (0.75 + 0.35 * u.haze);

    // haze in the air, lit by the moon and the candle
    let hazeLight = moonCol * 0.12 * (1.0 - L * 0.6) + warm * spillFall * F * 0.12;
    let wisp = smoothstep(0.35, 0.85, smoke);
    col = col + hazeLight * wisp * u.haze * 0.65;

    // vignette, deeper by candlelight
    let v = length((uv - vec2<f32>(0.42, 0.52)) * vec2<f32>(1.0, 0.85));
    col = col * mix(mix(1.0, smoothstep(1.0, 0.2, v), 0.35 + 0.5 * L), 1.0, cut * 0.85);

    // grain
    let gr = hash2(px + vec2<f32>(fract(t * 13.0) * 100.0, fract(t * 7.0) * 100.0)) - 0.5;
    col = col + gr * 0.03;

    // filmic curve
    col = col / (col + vec3<f32>(0.8)) * 1.65;
    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
