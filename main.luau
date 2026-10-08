-- Hollow: carve a pumpkin, light it, and watch what it throws into the dark.
--
-- Every frame the room is drawn into four canvases:
--   albedo  what things are made of (wall, table, pumpkin rind, fallen pieces)
--   mask    what has been carved: R = cut through, G = etched or cut, B = rind
--   maskLo  the same mask at quarter size, for the glow and the light rays
--   ghost   the thing on the wall that you did not carve (quarter size)
--   emit    what shines on its own (the window, the moon)
-- light.wgsl then lights the room with moonlight and the candle inside the
-- pumpkin: the holes glow, etched skin turns translucent, the rind warms near
-- every cut and rays stream through the haze. The result is drawn back into
-- the artboard under the markup.
--
-- The markup owns the words and the controls. They talk through the view
-- model: tool, lit, stencil, fresh, flame and haze come in; escape, the
-- readouts and the caption go out.

local W = 1280
local H = 800

-- the pumpkin, in design units
local PX = 500
local PY = 452
local RX = 258
local RY = 204
-- the face you can carve: an ellipse on the front of the pumpkin
local FX = 0
local FY = 12
local FRX = 214
local FRY = 160

-- the sliders the script drives (their markup sits at the same place)
local SL_X0 = 1000
local SL_X1 = 1216
local SL_FLAME_Y = 492
local SL_HAZE_Y = 560

type Pt = { x: number, y: number }

type Cut = {
    kind: string, -- 'hole' | 'slit' | 'etch' | 'etchfill'
    pts: { Pt },
    path: Path,
    area: number,
}

type Chunk = {
    pts: { Pt }, -- relative to its centre, pumpkin-local scale
    x: number, y: number, vx: number, vy: number,
    rot: number, vr: number,
    landY: number,
    landed: boolean,
    flesh: boolean, -- landed flesh side up
    age: number,
}

type Job = { kind: string, pts: { Pt }, closed: boolean }

type Puff = { x: number, y: number, vx: number, vy: number, life: number, max: number, r: number }

type Scene = {
    ctx: Context,
    size: Vector,
    q: number,
    t: number,
    -- input
    mouse: Pt,
    mouseIn: boolean,
    speed: number,
    lastMx: number,
    lastMy: number,
    lastMt: number,
    drag: string, -- '' | 'stroke' | 'flame' | 'haze'
    stroke: { Pt },
    -- carving
    cuts: { Cut },
    chunks: { Chunk },
    puffs: { Puff },
    jobs: { Job },
    job: Job?,
    jobT: number,
    jobLen: number,
    jobSpeed: number,
    knife: Pt,
    knifeOn: number,
    holes: number,
    open: number,
    jiggle: number,
    jiggleV: number,
    -- light
    lit: boolean,
    litT: number, -- seconds since lit / snuffed
    litAmt: number,
    flameAmt: number,
    flicker: number,
    lean: number,
    leanV: number,
    gust: number,
    phantom: number,
    phantomHold: number,
    blink: number,
    flameSet: number,
    hazeSet: number,
    tool: number,
    story: number,
    seed: number,
    -- gpu
    albedo: Canvas?,
    mask: Canvas?,
    maskLo: Canvas?,
    ghost: Canvas?,
    emit: Canvas?,
    gpu: GPUCanvas?,
    pipeline: GPUPipeline?,
    ubo: GPUBuffer?,
    bind: GPUBindGroup?,
    sampler: GPUSampler,
    data: buffer,
    paint: Paint,
    line: Paint,
    -- static geometry, pumpkin-local
    lobes: { { path: Path, cx: number, cy: number, w: number, h: number, shade: number } },
    silhouette: Path,
    face: Path,
    grooves: { Path },
    stem: Path,
    lid: Path,
    -- view model
    vmTool: Property<number>?,
    vmLit: Property<boolean>?,
    vmStencil: Property<number>?,
    vmFresh: Property<number>?,
    vmFlame: Property<number>?,
    vmHaze: Property<number>?,
    vmEscape: Property<number>?,
    vmEscapeText: Property<string>?,
    vmFlameText: Property<string>?,
    vmHazeText: Property<string>?,
    vmCaption: Property<string>?,
    vmQuality: Property<number>?,
    caption: string,
    -- the hover halo in the panel: spring state, then the view model
    halo: { number }, -- x, y, w, h, vx, vy, vw, vh
    haloOn: number,
    haloPress: number,
    vmHalo: { Property<number>? },
}

-- the panel controls the halo can settle on (centre x, centre y, w, h);
-- these mirror tools/gen_scene.py
local CONTROLS = {
    { 1054, 102, 104, 40 }, { 1162, 102, 104, 40 },
    { 1108, 189, 216, 42 }, { 1108, 239, 216, 42 }, { 1108, 289, 216, 42 },
    { 1108, 378, 216, 56 },
    { 1108, 707, 216, 46 },
}

-- ---------------------------------------------------------------------------
-- helpers

local function clamp01(v: number): number
    return if v < 0 then 0 elseif v > 1 then 1 else v
end

local function hash(n: number): number
    local s = math.sin(n * 12.9898 + 78.233) * 43758.5453
    return s - math.floor(s)
end

local function easeInOut(v: number): number
    local x = clamp01(v)
    return if x < 0.5 then 4 * x * x * x else 1 - (-2 * x + 2) ^ 3 / 2
end

local function rgb(r: number, g: number, b: number): Color
    return Color.rgb(r, g, b)
end

local function pt(x: number, y: number): Pt
    return { x = x, y = y }
end

-- Script paths fill with the clockwise rule: a contour that runs
-- counter-clockwise on screen draws nothing. Every polygon we fill goes
-- through here first (y points down, so a positive shoelace sum is clockwise).
local function cw(pts: { Pt }): { Pt }
    local a = 0
    local n = #pts
    for i = 1, n do
        local p = pts[i]
        local q = pts[(i % n) + 1]
        a += p.x * q.y - q.x * p.y
    end
    if a >= 0 then
        return pts
    end
    local out = {}
    for i = n, 1, -1 do
        table.insert(out, pts[i])
    end
    return out
end

-- points along a cubic bezier, for shapes that must be polygons
local function bez(out: { Pt }, a: Pt, b: Pt, c: Pt, d: Pt, n: number)
    for i = 1, n do
        local t = i / n
        local u = 1 - t
        local x = u * u * u * a.x + 3 * u * u * t * b.x + 3 * u * t * t * c.x + t * t * t * d.x
        local y = u * u * u * a.y + 3 * u * u * t * b.y + 3 * u * t * t * c.y + t * t * t * d.y
        table.insert(out, pt(x, y))
    end
end

local function polyPath(pts: { Pt }, closed: boolean): Path
    local p = Path.new()
    for i, q in pts do
        if i == 1 then
            p:moveTo(Vector.xy(q.x, q.y))
        else
            p:lineTo(Vector.xy(q.x, q.y))
        end
    end
    if closed then
        p:close()
    end
    return p
end

local function ellipsePath(p: Path, cx: number, cy: number, rx: number, ry: number)
    local k = 0.5523
    p:moveTo(Vector.xy(cx + rx, cy))
    p:cubicTo(Vector.xy(cx + rx, cy + ry * k), Vector.xy(cx + rx * k, cy + ry), Vector.xy(cx, cy + ry))
    p:cubicTo(Vector.xy(cx - rx * k, cy + ry), Vector.xy(cx - rx, cy + ry * k), Vector.xy(cx - rx, cy))
    p:cubicTo(Vector.xy(cx - rx, cy - ry * k), Vector.xy(cx - rx * k, cy - ry), Vector.xy(cx, cy - ry))
    p:cubicTo(Vector.xy(cx + rx * k, cy - ry), Vector.xy(cx + rx, cy - ry * k), Vector.xy(cx + rx, cy))
    p:close()
end

local function polyArea(pts: { Pt }): number
    local a = 0
    local n = #pts
    for i = 1, n do
        local p = pts[i]
        local q = pts[(i % n) + 1]
        a += p.x * q.y - q.x * p.y
    end
    return math.abs(a) / 2
end

local function polyLen(pts: { Pt }, closed: boolean): number
    local l = 0
    for i = 2, #pts do
        l += math.sqrt((pts[i].x - pts[i - 1].x) ^ 2 + (pts[i].y - pts[i - 1].y) ^ 2)
    end
    if closed and #pts > 1 then
        l += math.sqrt((pts[1].x - pts[#pts].x) ^ 2 + (pts[1].y - pts[#pts].y) ^ 2)
    end
    return l
end

-- the point a distance d along a polyline, and how far the line runs
local function along(pts: { Pt }, closed: boolean, d: number): (Pt, number)
    local acc = 0
    local n = #pts
    local last = if closed then n + 1 else n
    for i = 2, last do
        local a = pts[i - 1]
        local b = pts[((i - 1) % n) + 1]
        local seg = math.sqrt((b.x - a.x) ^ 2 + (b.y - a.y) ^ 2)
        if acc + seg >= d and seg > 0 then
            local f = (d - acc) / seg
            return pt(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f), i
        end
        acc += seg
    end
    local e = if closed then pts[1] else pts[n]
    return pt(e.x, e.y), last + 1
end

local function inFace(x: number, y: number): boolean
    local dx = (x - FX) / FRX
    local dy = (y - FY) / FRY
    return dx * dx + dy * dy <= 1
end

-- design units -> pumpkin-local, honouring the jiggle squash
local function toLocal(self: Scene, x: number, y: number): Pt
    local sx = 1 + self.jiggle * 0.5
    local sy = 1 - self.jiggle
    return pt((x - PX) / sx, (y - (PY + RY)) / sy + RY)
end

local function toWorld(self: Scene, x: number, y: number): Pt
    local sx = 1 + self.jiggle * 0.5
    local sy = 1 - self.jiggle
    return pt(PX + x * sx, PY + RY + (y - RY) * sy)
end

-- ---------------------------------------------------------------------------
-- stencils, pumpkin-local

local function mirror(pts: { Pt }): { Pt }
    local out = {}
    for i = #pts, 1, -1 do
        table.insert(out, pt(-pts[i].x, pts[i].y))
    end
    return out
end

local function star8(cx: number, cy: number, r1: number, r2: number): { Pt }
    local out = {}
    for k = 0, 15 do
        local a = k * math.pi / 8 + math.pi / 16
        local r = if k % 2 == 0 then r1 else r2
        table.insert(out, pt(cx + math.cos(a) * r, cy + math.sin(a) * r))
    end
    return out
end

local function grinJobs(): { Job }
    local eye = { pt(-150, -28), pt(-112, -104), pt(-54, -50), pt(-92, -36) }
    local nose = { pt(-20, 22), pt(0, -14), pt(20, 22), pt(0, 30) }
    local mouth = {}
    -- the upper lip, left to right, with two teeth hanging into the mouth
    local n = 16
    for i = 0, n do
        local u = i / n * 2 - 1
        local y = 34 + 40 * (1 - u * u)
        if (u > -0.46 and u < -0.2) or (u > 0.2 and u < 0.46) then
            y += 28
        end
        table.insert(mouth, pt(u * 172, y))
    end
    -- the lower lip, right to left, with one tooth standing up
    for i = n - 1, 1, -1 do
        local u = i / n * 2 - 1
        local y = 34 + 118 * (1 - u * u)
        if u > -0.13 and u < 0.13 then
            y -= 32
        end
        table.insert(mouth, pt(u * 164, y))
    end
    return {
        { kind = 'cut', pts = eye, closed = true },
        { kind = 'cut', pts = mirror(eye), closed = true },
        { kind = 'cut', pts = nose, closed = true },
        { kind = 'cut', pts = mouth, closed = true },
    }
end

local function ghoulJobs(): { Job }
    local eye = {}
    -- a sharp crescent, lower edge bowed down, upper edge nearly flat
    for i = 0, 12 do
        local u = i / 12
        table.insert(eye, pt(-170 + u * 120, -40 - 40 * u + 30 * math.sin(u * math.pi) * 0.0))
    end
    for i = 12, 0, -1 do
        local u = i / 12
        table.insert(eye, pt(-170 + u * 120, -40 - 40 * u + 48 * math.sin(u * math.pi)))
    end
    local mouth = {}
    local n = 9
    for i = 0, n do
        local u = i / n * 2 - 1
        local x = u * 128
        local y = 40 + 20 * u * u
        table.insert(mouth, pt(x, y + (if i % 2 == 0 then 0 else 30)))
    end
    for i = n, 0, -1 do
        local u = i / n * 2 - 1
        local x = u * 120
        local y = 150 - 30 * u * u
        table.insert(mouth, pt(x, y - (if i % 2 == 0 then 0 else 34)))
    end
    local brow = {}
    for i = 0, 8 do
        local u = i / 8
        table.insert(brow, pt(-190 + u * 150, -78 - 56 * u))
    end
    local cheek = {}
    for i = 0, 8 do
        local u = i / 8
        table.insert(cheek, pt(-182 + u * 30, 10 + u * 90))
    end
    return {
        { kind = 'etch', pts = brow, closed = false },
        { kind = 'etch', pts = mirror(brow), closed = false },
        { kind = 'etch', pts = cheek, closed = false },
        { kind = 'etch', pts = mirror(cheek), closed = false },
        { kind = 'cut', pts = eye, closed = true },
        { kind = 'cut', pts = mirror(eye), closed = true },
        { kind = 'cut', pts = { pt(-16, -6), pt(16, -6), pt(0, 18) }, closed = true },
        { kind = 'cut', pts = mouth, closed = true },
    }
end

-- a mashrabiya: the carved wooden screens of old Beirut houses
local function mashrabiyaJobs(): { Job }
    local jobs = {}
    local step = 64
    for row = -3, 3 do
        for col = -4, 4 do
            local x = col * step + (if row % 2 == 0 then 0 else step / 2)
            local y = FY + row * step * 0.82
            local dx = x / (FRX - 34)
            local dy = (y - FY) / (FRY - 30)
            if dx * dx + dy * dy <= 1 then
                table.insert(jobs, { kind = 'cut', pts = star8(x, y, 23, 15), closed = true })
            end
        end
    end
    -- etched diamonds between the stars
    for row = -3, 3 do
        for col = -4, 4 do
            local x = col * step + (if row % 2 == 0 then step / 2 else 0)
            local y = FY + row * step * 0.82
            local dx = x / (FRX - 20)
            local dy = (y - FY) / (FRY - 18)
            if dx * dx + dy * dy <= 1 then
                table.insert(jobs, {
                    kind = 'etchfill',
                    pts = { pt(x, y - 12), pt(x + 9, y), pt(x, y + 12), pt(x - 9, y) },
                    closed = true,
                })
            end
        end
    end
    -- a carved ring around the screen
    local ring = {}
    for k = 0, 48 do
        local a = k / 48 * math.pi * 2
        table.insert(ring, pt(FX + math.cos(a) * (FRX - 6), FY + math.sin(a) * (FRY - 6)))
    end
    table.insert(jobs, 1, { kind = 'etch', pts = ring, closed = false })
    return jobs
end

-- ---------------------------------------------------------------------------
-- geometry

local function buildPumpkin(self: Scene)
    self.lobes = {}
    local defs = {
        { -3, 0.86, 0.40 }, { 3, 0.86, 0.40 },
        { -2, 0.95, 0.62 }, { 2, 0.95, 0.62 },
        { -1, 0.99, 0.82 }, { 1, 0.99, 0.82 },
        { 0, 1.0, 1.0 },
    }
    for _, d in defs do
        local i = d[1]
        local cx = i * RX * 0.235
        local w = RX * (0.40 - math.abs(i) * 0.035)
        local h = RY * d[2]
        local cy = RY * (1 - d[2]) * 0.55
        local p = Path.new()
        ellipsePath(p, cx, cy, w, h)
        table.insert(self.lobes, { path = p, cx = cx, cy = cy, w = w, h = h, shade = d[3] })
    end
    local sil = Path.new()
    for _, l in self.lobes do
        ellipsePath(sil, l.cx, l.cy, l.w, l.h)
    end
    self.silhouette = sil
    local face = Path.new()
    ellipsePath(face, FX, FY, FRX, FRY)
    self.face = face
    self.grooves = {}
    for i = -3, 2 do
        local x = (i + 0.5) * RX * 0.235
        local hh = RY * (0.97 - math.abs(i + 0.5) * 0.03)
        local bow = (i + 0.5) * 9
        local g = Path.new()
        g:moveTo(Vector.xy(x * 0.3, -hh + 14))
        g:cubicTo(Vector.xy(x + bow, -hh * 0.6), Vector.xy(x + bow, hh * 0.6), Vector.xy(x * 0.5, hh - 4))
        table.insert(self.grooves, g)
    end
    local stem = Path.new()
    stem:moveTo(Vector.xy(-18, -RY + 18))
    stem:cubicTo(Vector.xy(-20, -RY - 20), Vector.xy(-6, -RY - 52), Vector.xy(20, -RY - 66))
    stem:lineTo(Vector.xy(30, -RY - 56))
    stem:cubicTo(Vector.xy(12, -RY - 40), Vector.xy(12, -RY - 14), Vector.xy(18, -RY + 18))
    stem:close()
    self.stem = stem
    -- the lid, cut in a zig-zag around the stem
    local lid = Path.new()
    local n = 22
    for k = 0, n do
        local u = k / n
        local a = math.pi * (1.05 + u * 0.9)
        local r = if k % 2 == 0 then 1 else 0.9
        local x = math.cos(a) * 92 * r
        local y = -RY + 34 + math.sin(a) * -30 * r + 30
        if k == 0 then
            lid:moveTo(Vector.xy(x, y))
        else
            lid:lineTo(Vector.xy(x, y))
        end
    end
    self.lid = lid
end

-- ---------------------------------------------------------------------------
-- view model

local function say(self: Scene, s: string)
    if self.caption == s then
        return
    end
    self.caption = s
    local c = self.vmCaption
    if c ~= nil then
        c.value = s
    end
end

local function bindVm(self: Scene, context: Context)
    local vm = context:viewModel()
    if vm == nil then
        return
    end
    self.vmTool = vm:getNumber('tool')
    self.vmLit = vm:getBoolean('lit')
    self.vmStencil = vm:getNumber('stencil')
    self.vmFresh = vm:getNumber('fresh')
    self.vmFlame = vm:getNumber('flame')
    self.vmHaze = vm:getNumber('haze')
    self.vmEscape = vm:getNumber('escape')
    self.vmEscapeText = vm:getString('escapeText')
    self.vmFlameText = vm:getString('flameText')
    self.vmHazeText = vm:getString('hazeText')
    self.vmCaption = vm:getString('caption')
    self.vmQuality = vm:getNumber('quality')
    self.vmHalo = {
        vm:getNumber('haloX'), vm:getNumber('haloY'), vm:getNumber('haloW'), vm:getNumber('haloH'),
        vm:getNumber('haloOn'), vm:getNumber('haloPress'),
    }
end

function init(self: Scene, context: Context): boolean
    self.ctx = context
    bindVm(self, context)
    if #self.lobes == 0 then
        buildPumpkin(self)
    end
    say(self, 'Draw with the knife. Close a shape and the piece falls out.')
    return true
end

local function rebuild(self: Scene)
    local q = self.q
    local w = math.max(1, math.floor(self.size.x * q))
    local h = math.max(1, math.floor(self.size.y * q))
    local lw = math.max(1, math.floor(w / 4))
    local lh = math.max(1, math.floor(h / 4))
    local ctx = self.ctx
    local albedo = ctx:canvas({ width = w, height = h })
    local mask = ctx:canvas({ width = w, height = h })
    local emit = ctx:canvas({ width = w, height = h })
    local maskLo = ctx:canvas({ width = lw, height = lh })
    local ghost = ctx:canvas({ width = math.max(1, math.floor(w / 2)), height = math.max(1, math.floor(h / 2)) })
    self.albedo = albedo
    self.mask = mask
    self.emit = emit
    self.maskLo = maskLo
    self.ghost = ghost
    local gpu = ctx:gpuCanvas({ width = w, height = h })
    self.gpu = gpu
    local shader = ctx:shader('light')
    if shader == nil then
        print('hollow: light shader missing')
        return
    end
    local pipeline = GPUPipeline.new({
        vertex = shader,
        fragment = shader,
        vertexLayout = {},
        colorTargets = { { format = gpu.format } },
    })
    self.pipeline = pipeline
    local ubo = GPUBuffer.new({ size = 112, usage = 'uniform' })
    self.ubo = ubo
    self.bind = GPUBindGroup.new({
        layout = pipeline:getBindGroupLayout(0),
        ubos = { { slot = 0, buffer = ubo } },
        textures = {
            { slot = 1, view = albedo.image:view() },
            { slot = 2, view = mask.image:view() },
            { slot = 3, view = maskLo.image:view() },
            { slot = 4, view = ghost.image:view() },
            { slot = 5, view = emit.image:view() },
        },
        samplers = { { slot = 6, sampler = self.sampler } },
    })
end

function resize(self: Scene, size: Vector)
    self.size = size
    rebuild(self)
end

-- design units <-> artboard units (the room is 1280x800, covered into any size)
local function fit(self: Scene): (number, number, number)
    local sx = self.size.x / W
    local sy = self.size.y / H
    local s = math.max(sx, sy)
    return s, (self.size.x - W * s) / 2, (self.size.y - H * s) / 2
end

-- ---------------------------------------------------------------------------
-- carving

local function addCut(self: Scene, kind: string, pts: { Pt }, closed: boolean)
    if #pts < 2 then
        return
    end
    if closed then
        pts = cw(pts)
    end
    local area = 0
    if kind == 'hole' or kind == 'etchfill' then
        area = polyArea(pts)
    else
        area = polyLen(pts, closed) * (if kind == 'slit' then 4 else 22)
    end
    table.insert(self.cuts, { kind = kind, pts = pts, path = polyPath(pts, closed), area = area })
    if kind == 'hole' then
        self.holes += 1
        -- the piece falls out
        local cx, cy = 0, 0
        for _, p in pts do
            cx += p.x
            cy += p.y
        end
        cx /= #pts
        cy /= #pts
        local rel = {}
        for _, p in pts do
            table.insert(rel, pt(p.x - cx, p.y - cy))
        end
        local w = toWorld(self, cx, cy)
        local s = self.seed
        self.seed += 1
        table.insert(self.chunks, {
            pts = rel,
            x = w.x, y = w.y,
            vx = (hash(s) - 0.5) * 160 + (w.x - PX) * 0.6,
            vy = -120 - hash(s + 1) * 120,
            rot = 0,
            vr = (hash(s + 2) - 0.5) * 9,
            landY = 662 + hash(s + 3) * 34,
            landed = false,
            flesh = hash(s + 4) > 0.45,
            age = 0,
        })
        while #self.chunks > 70 do
            table.remove(self.chunks, 1)
        end
        self.jiggleV += 0.9
    end
end

local function finishStroke(self: Scene)
    local s = self.stroke
    self.stroke = {}
    if #s < 2 then
        return
    end
    if self.tool == 1 then
        addCut(self, 'etch', s, false)
        return
    end
    local first = s[1]
    local last = s[#s]
    local gap = math.sqrt((last.x - first.x) ^ 2 + (last.y - first.y) ^ 2)
    local len = polyLen(s, false)
    if gap < 34 and len > 90 and polyArea(s) > 300 then
        addCut(self, 'hole', s, true)
    else
        addCut(self, 'slit', s, false)
    end
end

local function startStencil(self: Scene, which: number)
    local jobs = if which == 1 then grinJobs() elseif which == 2 then ghoulJobs() else mashrabiyaJobs()
    for _, j in jobs do
        table.insert(self.jobs, j)
    end
    self.jobSpeed = if which == 3 then 2600 else 820
    if which == 3 then
        say(self, 'A mashrabiya, cut like the wooden screens of old Beirut houses.')
    end
end

local function fresh(self: Scene)
    self.cuts = {}
    self.chunks = {}
    self.jobs = {}
    self.job = nil
    self.stroke = {}
    self.holes = 0
    self.open = 0
    self.phantom = 0
    self.phantomHold = 0
    self.story = 0
    self.jiggleV += 1.4
    if self.lit then
        self.lit = false
        self.litT = 0
        local vl = self.vmLit
        if vl ~= nil then
            vl.value = false
        end
    end
    say(self, 'A fresh one. Nothing has looked out of it yet.')
end

-- ---------------------------------------------------------------------------
-- input

local function design(self: Scene, event: PointerEvent): Pt
    local s, ox, oy = fit(self)
    return pt((event.position.x - ox) / s, (event.position.y - oy) / s)
end

local function setSlider(self: Scene, which: string, x: number)
    local v = clamp01((x - SL_X0) / (SL_X1 - SL_X0)) * 100
    if which == 'flame' then
        local p = self.vmFlame
        if p ~= nil then
            p.value = v
        end
        self.flameSet = v
    else
        local p = self.vmHaze
        if p ~= nil then
            p.value = v
        end
        self.hazeSet = v
    end
end

local function controlAt(x: number, y: number): { number }?
    for _, c in CONTROLS do
        if math.abs(x - c[1]) <= c[3] / 2 and math.abs(y - c[2]) <= c[4] / 2 then
            return c
        end
    end
    return nil
end

function pointerDown(self: Scene, event: PointerEvent)
    local p = design(self, event)
    self.mouse = p
    self.mouseIn = true
    if controlAt(p.x, p.y) ~= nil then
        self.haloPress = 1
    end
    if p.x > SL_X0 - 14 and p.x < SL_X1 + 14 then
        if math.abs(p.y - SL_FLAME_Y) < 16 then
            self.drag = 'flame'
            setSlider(self, 'flame', p.x)
            event:hit()
            return
        elseif math.abs(p.y - SL_HAZE_Y) < 16 then
            self.drag = 'haze'
            setSlider(self, 'haze', p.x)
            event:hit()
            return
        end
    end
    local l = toLocal(self, p.x, p.y)
    if inFace(l.x, l.y) and self.job == nil and #self.jobs == 0 then
        self.drag = 'stroke'
        self.stroke = { l }
        event:hit()
    end
end

function pointerMove(self: Scene, event: PointerEvent)
    local p = design(self, event)
    local dt = self.t - self.lastMt
    if dt > 0.001 then
        local d = math.sqrt((p.x - self.lastMx) ^ 2 + (p.y - self.lastMy) ^ 2)
        local v = d / dt
        self.speed = math.max(self.speed * 0.5, v)
        -- a hand swept past the pumpkin: the flame leans away from it
        local near = math.sqrt((p.x - PX) ^ 2 + (p.y - PY) ^ 2)
        if near < 420 then
            self.leanV += clamp01(math.abs(p.x - self.lastMx) / 60) * (if p.x > self.lastMx then 1 else -1) * 3
        end
        self.lastMx = p.x
        self.lastMy = p.y
        self.lastMt = self.t
    end
    self.mouse = p
    self.mouseIn = true
    if self.drag == 'flame' or self.drag == 'haze' then
        setSlider(self, self.drag, p.x)
        event:hit()
    elseif self.drag == 'stroke' then
        local l = toLocal(self, p.x, p.y)
        local s = self.stroke
        local last = s[#s]
        if math.sqrt((l.x - last.x) ^ 2 + (l.y - last.y) ^ 2) > 3 then
            table.insert(s, l)
        end
        event:hit()
    end
end

function pointerUp(self: Scene, event: PointerEvent)
    if self.drag == 'stroke' then
        finishStroke(self)
        event:hit()
    elseif self.drag ~= '' then
        event:hit()
    end
    self.drag = ''
end

function pointerExit(self: Scene, event: PointerEvent)
    self.mouseIn = false
    if self.drag == 'stroke' then
        finishStroke(self)
    end
    self.drag = ''
end

-- ---------------------------------------------------------------------------
-- time

local function readVm(self: Scene)
    local vt = self.vmTool
    if vt ~= nil then
        self.tool = vt.value
    end
    local vl = self.vmLit
    if vl ~= nil and vl.value ~= self.lit then
        self.lit = vl.value
        self.litT = 0
        if self.lit then
            if self.holes + #self.cuts == 0 then
                say(self, 'Lit. But nothing gets out of a pumpkin you have not carved.')
            else
                say(self, 'There. Look at what it throws into the dark.')
            end
        else
            -- snuffed: a curl of smoke out of the lid
            for k = 1, 14 do
                table.insert(self.puffs, {
                    x = PX + (hash(k + self.t) - 0.5) * 40, y = PY - RY + 30,
                    vx = (hash(k * 3 + self.t) - 0.5) * 30, vy = -40 - hash(k * 7) * 50,
                    life = -k * 0.09, max = 2.6, r = 10 + hash(k * 5) * 10,
                })
            end
            if self.phantom > 0.3 then
                self.phantomHold = 1.6
                say(self, 'Smoke. Silence. And it is still looking at you.')
            else
                say(self, 'Smoke. Silence. Carve some more?')
            end
        end
    end
    local vs = self.vmStencil
    if vs ~= nil and vs.value ~= 0 then
        startStencil(self, vs.value)
        vs.value = 0
    end
    local vf = self.vmFresh
    if vf ~= nil and vf.value ~= 0 then
        fresh(self)
        vf.value = 0
    end
    local fl = self.vmFlame
    if fl ~= nil then
        self.flameSet = fl.value
    end
    local hz = self.vmHaze
    if hz ~= nil then
        self.hazeSet = hz.value
    end
    local vq = self.vmQuality
    if vq ~= nil and vq.value > 0 and vq.value ~= self.q then
        self.q = vq.value
        rebuild(self)
    end
end

local function runJobs(self: Scene, dt: number)
    local job = self.job
    if job == nil then
        if #self.jobs == 0 then
            return
        end
        local nextJob: Job = table.remove(self.jobs, 1) :: Job
        job = nextJob
        self.job = nextJob
        self.jobT = 0
        self.jobLen = polyLen(nextJob.pts, nextJob.closed)
    end
    if job == nil then
        return
    end
    self.jobT += dt
    local d = self.jobT * self.jobSpeed
    local k, _ = along(job.pts, job.closed, math.min(d, self.jobLen))
    self.knife = k
    if d >= self.jobLen then
        if job.kind == 'cut' then
            addCut(self, if job.closed then 'hole' else 'slit', job.pts, job.closed)
        else
            addCut(self, job.kind, job.pts, job.closed)
        end
        self.job = nil
    end
end

local function storyBeat(self: Scene)
    if self.lit then
        return
    end
    if self.story == 0 and self.holes >= 1 and #self.jobs == 0 and self.job == nil then
        self.story = 1
        say(self, 'Good. Give it eyes, then a mouth.')
    elseif self.story <= 1 and self.holes >= 3 and #self.jobs == 0 and self.job == nil then
        self.story = 2
        say(self, 'Now light the candle.')
    end
end

function advance(self: Scene, seconds: number): boolean
    local dt = math.min(seconds, 1 / 20)
    self.t += dt
    self.litT += dt
    readVm(self)
    runJobs(self, dt)
    storyBeat(self)

    -- the pumpkin jiggles when a piece pops out (a soft, slightly underdamped spring)
    local acc = -self.jiggle * 520 - self.jiggleV * 15
    self.jiggleV += acc * dt
    self.jiggle += self.jiggleV * dt * 0.02

    -- how much light can escape
    local open = 0
    for _, c in self.cuts do
        open += if c.kind == 'hole' then c.area elseif c.kind == 'slit' then c.area else c.area * 0.25
    end
    local faceArea = math.pi * FRX * FRY
    self.open = clamp01(open / (faceArea * 0.22))

    -- the candle: lighting overshoots like a struck match, then settles
    local flameTarget = 0
    if self.lit then
        local t = self.litT
        local strike = (1 - math.exp(-t * 16)) * (1 + 0.55 * math.exp(-t * 3.6) * math.cos(t * 10.5))
        flameTarget = strike
        self.litAmt = easeInOut(t / 1.5)
    else
        local t = self.litT
        flameTarget = 0
        self.litAmt = math.min(self.litAmt, 1 - easeInOut(t / 1.1))
    end
    local kf = 1 - math.exp(-dt * (if self.lit then 40 else 14))
    self.flameAmt += (flameTarget - self.flameAmt) * kf
    local n = math.sin(self.t * 11.3) * 0.5 + math.sin(self.t * 17.9 + 1.7) * 0.35 + math.sin(self.t * 31.1 + 0.3) * 0.15
    self.flicker = 0.88 + 0.08 * n + (hash(math.floor(self.t * 24)) - 0.5) * 0.05

    -- a fast hand near the flame is a gust
    if self.lit and self.speed > 2600 then
        local near = math.sqrt((self.mouse.x - PX) ^ 2 + (self.mouse.y - PY) ^ 2)
        if near < 340 and self.gust < 0.3 then
            self.gust = 1
            if self.phantom > 0.5 then
                say(self, 'Easy. It does not like the dark either.')
            else
                say(self, 'Careful. One breath and it is out.')
            end
        end
    end
    self.speed *= math.exp(-dt * 10)
    self.gust = math.max(0, self.gust - dt * 0.9)
    -- the lean is a spring the hand keeps kicking
    local la = -self.lean * 60 - self.leanV * 7
    self.leanV += la * dt
    self.lean += self.leanV * dt
    self.lean = math.max(-1, math.min(1, self.lean))

    -- the thing on the wall
    local wantPhantom = self.lit and self.litT > 6 and self.holes >= 2 and self.gust < 0.2
    if wantPhantom then
        if self.phantom < 0.05 and self.story < 3 then
            self.story = 3
            say(self, 'Wait. You did not carve that.')
        end
        self.phantom = math.min(1, self.phantom + dt * 0.45)
    elseif self.phantomHold > 0 then
        self.phantomHold -= dt
    else
        self.phantom = math.max(0, self.phantom - dt * (if self.gust > 0.2 then 2.2 else 0.9))
    end
    self.blink += dt

    -- the knife eases toward the pointer, or rides the stencil
    local goal = self.mouse
    local showKnife = 0
    if self.job ~= nil then
        local w = toWorld(self, self.knife.x, self.knife.y)
        goal = w
        showKnife = 1
    else
        local l = toLocal(self, self.mouse.x, self.mouse.y)
        local dx = (l.x - FX) / (FRX + 60)
        local dy = (l.y - FY) / (FRY + 60)
        if self.mouseIn and dx * dx + dy * dy <= 1 then
            showKnife = 1
        end
    end
    if self.job ~= nil then
        self.knife = goal
    end
    self.knifeOn += (showKnife - self.knifeOn) * (1 - math.exp(-dt * 14))

    -- fallen pieces
    for _, c in self.chunks do
        c.age += dt
        if not c.landed then
            c.vy += 1700 * dt
            c.x += c.vx * dt
            c.y += c.vy * dt
            c.rot += c.vr * dt
            if c.y >= c.landY and c.vy > 0 then
                c.y = c.landY
                if c.vy > 380 then
                    c.vy = -c.vy * 0.28
                    c.vx *= 0.6
                    c.vr *= 0.5
                else
                    c.landed = true
                    -- it settles flat, on whichever face it fell
                    c.rot = math.floor(c.rot / math.pi + 0.5) * math.pi + (hash(c.x) - 0.5) * 0.5
                end
            end
        end
    end
    for i = #self.puffs, 1, -1 do
        local p = self.puffs[i]
        p.life += dt
        if p.life > 0 then
            p.x += p.vx * dt + math.sin(p.life * 3 + i) * 12 * dt
            p.y += p.vy * dt
            p.vy *= 0.99
            p.r += dt * 14
        end
        if p.life > p.max then
            table.remove(self.puffs, i)
        end
    end

    -- the halo glides to the control under the pointer: a spring tuned by eye
    -- to overshoot a hair and settle in about a fifth of a second
    local found = if self.mouseIn then controlAt(self.mouse.x, self.mouse.y) else nil
    local h = self.halo
    if found ~= nil then
        local c: { number } = found
        if self.haloOn < 0.05 then
            -- appear in place rather than flying in from the last control
            h[1], h[2], h[3], h[4] = c[1], c[2], c[3], c[4]
        end
        for i = 1, 4 do
            local pull = (c[i] - h[i]) * 620 - h[i + 4] * 34
            h[i + 4] += pull * dt
            h[i] += h[i + 4] * dt
        end
    end
    local onTarget = if found ~= nil then 1 else 0
    self.haloOn += (onTarget - self.haloOn) * (1 - math.exp(-dt * (if found ~= nil then 16 else 9)))
    self.haloPress = math.max(0, self.haloPress - dt * 5)
    local vh = self.vmHalo
    local vals = { h[1], h[2], h[3], h[4], self.haloOn, self.haloPress * self.haloPress }
    for i = 1, 6 do
        local p = vh[i]
        if p ~= nil then
            p.value = vals[i]
        end
    end

    -- readouts
    local pct = math.floor(self.open * 100 + 0.5)
    local ve = self.vmEscape
    if ve ~= nil then
        ve.value = pct
    end
    local vet = self.vmEscapeText
    if vet ~= nil then
        vet.value = tostring(pct) .. '%'
    end
    local vft = self.vmFlameText
    if vft ~= nil then
        vft.value = tostring(math.floor(self.flameSet + 0.5))
    end
    local vht = self.vmHazeText
    if vht ~= nil then
        vht.value = tostring(math.floor(self.hazeSet + 0.5))
    end
    return true
end

-- ---------------------------------------------------------------------------
-- drawing

local function fill(self: Scene, r: Renderer, p: Path, c: Color)
    self.paint.color = c
    r:drawPath(p, self.paint)
end

local function rect(x: number, y: number, w: number, h: number): Path
    local p = Path.new()
    p:moveTo(Vector.xy(x, y))
    p:lineTo(Vector.xy(x + w, y))
    p:lineTo(Vector.xy(x + w, y + h))
    p:lineTo(Vector.xy(x, y + h))
    p:close()
    return p
end

local function ellipse(cx: number, cy: number, rx: number, ry: number): Path
    local p = Path.new()
    ellipsePath(p, cx, cy, rx, ry)
    return p
end


-- a soft blob: an elliptical radial gradient fading to nothing (feather is not
-- reliable in offscreen canvases, so glows and shadows are gradients)
local function soft(self: Scene, r: Renderer, cx: number, cy: number, rx: number, ry: number, c: { number }, a: number)
    r:save()
    r:transform(Mat2D.values(rx / ry, 0, 0, 1, cx, cy))
    self.paint.gradient = Gradient.radial(Vector.xy(0, 0), ry, {
        { position = 0, color = Color.rgba(c[1], c[2], c[3], math.floor(a * 255)) },
        { position = 0.55, color = Color.rgba(c[1], c[2], c[3], math.floor(a * 0.45 * 255)) },
        { position = 1, color = Color.rgba(c[1], c[2], c[3], 0) },
    })
    r:drawPath(ellipse(0, 0, ry, ry), self.paint)
    self.paint.gradient = nil
    r:restore()
end

local function pumpkinXf(self: Scene, r: Renderer)
    local sx = 1 + self.jiggle * 0.5
    local sy = 1 - self.jiggle
    r:transform(Mat2D.values(sx, 0, 0, sy, PX, PY + RY - RY * sy))
end

local function drawRoom(self: Scene, r: Renderer)
    local paint = self.paint
    -- plaster wall, lighter toward the table
    paint.gradient = Gradient.linear(Vector.xy(0, 0), Vector.xy(0, 640), {
        { position = 0, color = rgb(84, 80, 86) },
        { position = 1, color = rgb(140, 128, 118) },
    })
    r:drawPath(rect(0, 0, W, 640), paint)
    paint.gradient = nil
    -- damp patches and old repairs in the plaster
    for k = 1, 11 do
        local x = hash(k * 1.7) * W
        local y = 40 + hash(k * 2.3) * 520
        soft(self, r, x, y, 80 + hash(k) * 140, 50 + hash(k + 9) * 90, { 60, 54, 58 }, 0.35)
    end
    for k = 1, 5 do
        soft(self, r, 200 + hash(k * 7.7) * 700, 80 + hash(k * 3.1) * 400, 90, 60, { 170, 160, 150 }, 0.18)
    end
    -- a crack running down from the ceiling
    self.line.color = Color.rgba(40, 34, 36, 150)
    self.line.thickness = 1.6
    local cr = Path.new()
    cr:moveTo(Vector.xy(812, 0))
    cr:lineTo(Vector.xy(806, 40))
    cr:lineTo(Vector.xy(818, 76))
    cr:lineTo(Vector.xy(809, 118))
    cr:lineTo(Vector.xy(822, 150))
    cr:moveTo(Vector.xy(818, 76))
    cr:lineTo(Vector.xy(836, 96))
    r:drawPath(cr, self.line)
    -- the window
    local wx, wy, ww, wh = 70, 150, 190, 330
    fill(self, r, rect(wx - 14, wy - 14, ww + 28, wh + 28), rgb(48, 38, 32))
    fill(self, r, rect(wx - 30, wy + wh + 10, ww + 60, 16), rgb(120, 104, 90))
    fill(self, r, rect(wx - 30, wy + wh + 26, ww + 60, 5), rgb(60, 50, 44))
    fill(self, r, rect(wx, wy, ww, wh), rgb(18, 22, 34))
    -- a wainscot rail
    fill(self, r, rect(0, 548, W, 8), rgb(96, 84, 76))
    fill(self, r, rect(0, 556, W, 3), rgb(56, 48, 44))
    -- table top
    paint.gradient = Gradient.linear(Vector.xy(0, 606), Vector.xy(0, 712), {
        { position = 0, color = rgb(84, 56, 38) },
        { position = 1, color = rgb(136, 92, 60) },
    })
    r:drawPath(rect(0, 606, W, 106), paint)
    paint.gradient = nil
    fill(self, r, rect(0, 712, W, 88), rgb(62, 40, 28))
    fill(self, r, rect(0, 708, W, 5), rgb(156, 112, 74))
    -- grain
    self.line.color = Color.rgba(46, 28, 18, 110)
    self.line.thickness = 1.2
    for k = 1, 15 do
        local y = 610 + k * 6.6
        local p = Path.new()
        p:moveTo(Vector.xy(0, y))
        local seg = 10
        for i = 1, seg do
            local x = i * W / seg
            p:lineTo(Vector.xy(x, y + math.sin(i * 1.3 + k * 2.1) * 1.4))
        end
        r:drawPath(p, self.line)
    end
    for k = 1, 6 do
        local y = 726 + k * 11
        local p = Path.new()
        p:moveTo(Vector.xy(0, y))
        p:cubicTo(Vector.xy(300, y + 3), Vector.xy(800, y - 4), Vector.xy(W, y + 2))
        r:drawPath(p, self.line)
    end
    -- a small gourd
    soft(self, r, 930, 676, 92, 16, { 14, 8, 6 }, 0.85)
    paint.gradient = Gradient.radial(Vector.xy(902, 626), 60, {
        { position = 0, color = rgb(232, 206, 120) },
        { position = 1, color = rgb(150, 118, 52) },
    })
    r:drawPath(ellipse(915, 640, 44, 36), paint)
    paint.gradient = Gradient.radial(Vector.xy(940, 634), 50, {
        { position = 0, color = rgb(214, 186, 100) },
        { position = 1, color = rgb(126, 98, 40) },
    })
    r:drawPath(ellipse(950, 646, 34, 29), paint)
    paint.gradient = nil
    fill(self, r, rect(924, 594, 6, 20), rgb(80, 74, 40))
    -- seeds
    for k = 1, 18 do
        local x = PX - 340 + hash(k * 4.1) * 130
        local y = 678 + hash(k * 3.3) * 46
        if k > 9 then
            x = PX + 220 + hash(k * 5.7) * 150
        end
        local p = Path.new()
        local a = hash(k * 2.9) * 3.1
        local ca, sa = math.cos(a), math.sin(a)
        p:moveTo(Vector.xy(x - 6 * ca, y - 6 * sa * 0.5))
        p:quadTo(Vector.xy(x + 4 * sa, y - 4 * ca * 0.5), Vector.xy(x + 6 * ca, y + 6 * sa * 0.5))
        p:quadTo(Vector.xy(x - 4 * sa, y + 4 * ca * 0.5), Vector.xy(x - 6 * ca, y - 6 * sa * 0.5))
        p:close()
        fill(self, r, p, rgb(238, 224, 184))
    end
    -- the pumpkin's shadow on the table
    soft(self, r, PX, PY + RY + 4, RX * 1.2, 42, { 10, 6, 4 }, 0.95)
end

local function drawPumpkin(self: Scene, r: Renderer)
    local paint = self.paint
    r:save()
    pumpkinXf(self, r)
    for _, l in self.lobes do
        local s = l.shade
        -- an elliptical gradient: draw a circle in a squashed space
        r:save()
        r:transform(Mat2D.values(l.w / l.h, 0, 0, 1, l.cx, l.cy))
        paint.gradient = Gradient.radial(Vector.xy(-l.h * 0.22, -l.h * 0.3), l.h * 1.22, {
            { position = 0, color = rgb(255, 156 + 22 * s, 64 + 10 * s) },
            { position = 0.35, color = rgb(232 + 14 * s, 108 + 16 * s, 22) },
            { position = 0.72, color = rgb(176 + 20 * s, 66 + 10 * s, 10) },
            { position = 1, color = rgb(88, 26, 4) },
        })
        r:drawPath(ellipse(0, 0, l.h, l.h), paint)
        r:restore()
    end
    paint.gradient = nil
    self.line.color = Color.rgba(92, 28, 4, 120)
    self.line.thickness = 3
    for _, g in self.grooves do
        r:drawPath(g, self.line)
    end
    -- glossy highlights on the front lobes
    for _, l in self.lobes do
        if l.shade > 0.5 then
            soft(self, r, l.cx - l.w * 0.32, l.cy - l.h * 0.5, l.w * 0.26, l.h * 0.16, { 255, 222, 170 }, 0.3 * l.shade)
            soft(self, r, l.cx - l.w * 0.42, l.cy + l.h * 0.05, l.w * 0.12, l.h * 0.36, { 255, 200, 140 }, 0.12 * l.shade)
        end
    end
    -- a darker band where the pumpkin meets the table
    soft(self, r, 0, RY * 0.92, RX * 0.9, RY * 0.2, { 40, 10, 2 }, 0.5)
    -- the lid line
    self.line.color = Color.rgba(60, 18, 2, 255)
    self.line.thickness = 3
    r:drawPath(self.lid, self.line)
    -- stem
    paint.gradient = Gradient.linear(Vector.xy(-20, -RY), Vector.xy(30, -RY - 60), {
        { position = 0, color = rgb(64, 60, 30) },
        { position = 0.6, color = rgb(120, 116, 70) },
        { position = 1, color = rgb(150, 140, 96) },
    })
    r:drawPath(self.stem, paint)
    paint.gradient = nil
    r:restore()
end

local function chunkPath(c: Chunk): Path
    local p = Path.new()
    local cs = math.cos(c.rot)
    local sn = math.sin(c.rot)
    -- pieces lie flatter once they land
    local flat = if c.landed then 0.42 else 1
    local sc = 0.62
    for i, q in c.pts do
        local x = c.x + (q.x * cs - q.y * sn) * sc
        local y = c.y + (q.x * sn + q.y * cs) * flat * sc
        if i == 1 then
            p:moveTo(Vector.xy(x, y))
        else
            p:lineTo(Vector.xy(x, y))
        end
    end
    p:close()
    return p
end

local function drawChunks(self: Scene, r: Renderer, asMask: boolean)
    for _, c in self.chunks do
        local p = chunkPath(c)
        if asMask then
            fill(self, r, p, rgb(0, 0, 0))
        else
            if c.landed then
                soft(self, r, c.x, c.y + 8, 26, 7, { 20, 10, 6 }, 0.7)
            end
            fill(self, r, p, if c.flesh then rgb(214, 150, 74) else rgb(196, 84, 18))
            self.line.color = if c.flesh then rgb(176, 70, 14) else rgb(214, 160, 90)
            self.line.thickness = 2
            r:drawPath(p, self.line)
        end
    end
end

local function knifePath(x: number, y: number, a: number, etch: boolean): (Path, Path)
    local cs = math.cos(a)
    local sn = math.sin(a)
    local function P(u: number, v: number): Vector
        return Vector.xy(x + u * cs - v * sn, y + u * sn + v * cs)
    end
    local blade = Path.new()
    local handle = Path.new()
    if etch then
        -- a loop gouge
        blade:moveTo(P(0, -6))
        blade:lineTo(P(10, -7))
        blade:lineTo(P(60, -2))
        blade:lineTo(P(60, 2))
        blade:lineTo(P(10, 7))
        blade:lineTo(P(0, 6))
        blade:close()
    else
        blade:moveTo(P(0, 0))
        blade:cubicTo(P(20, -3), P(46, -12), P(78, -12))
        blade:lineTo(P(78, 4))
        blade:lineTo(P(14, 4))
        blade:close()
    end
    handle:moveTo(P(76, -10))
    handle:lineTo(P(138, -9))
    handle:cubicTo(P(148, -8), P(148, 7), P(138, 8))
    handle:lineTo(P(76, 6))
    handle:close()
    return blade, handle
end

local function drawKnife(self: Scene, r: Renderer, asMask: boolean)
    if self.knifeOn < 0.02 then
        return
    end
    local k = if self.job ~= nil then self.knife else self.mouse
    local a = -0.8 + math.sin(self.t * 2) * 0.03
    local blade, handle = knifePath(k.x, k.y, a, self.tool == 1 and self.job == nil)
    if asMask then
        fill(self, r, blade, rgb(0, 0, 0))
        fill(self, r, handle, rgb(0, 0, 0))
        return
    end
    local o = math.floor(self.knifeOn * 255)
    fill(self, r, blade, Color.rgba(220, 224, 230, o))
    fill(self, r, handle, Color.rgba(70, 40, 26, o))
    self.line.color = Color.rgba(255, 255, 255, math.floor(o * 0.6))
    self.line.thickness = 1.2
    r:drawPath(blade, self.line)
end

local function drawCuts(self: Scene, r: Renderer)
    local live = self.stroke
    r:save()
    pumpkinXf(self, r)
    -- rind
    fill(self, r, self.silhouette, rgb(0, 0, 255))
    -- the lid gap: a hairline of light when lit
    self.line.color = rgb(0, 255, 255)
    self.line.thickness = 2.2
    r:drawPath(self.lid, self.line)
    r:clipPath(self.face)
    local etch = Color.rgb(0, 255, 255)
    local cut = Color.rgb(255, 255, 255)
    self.line.thickness = 22
    self.line.color = etch
    for _, c in self.cuts do
        if c.kind == 'etch' then
            r:drawPath(c.path, self.line)
        elseif c.kind == 'etchfill' then
            fill(self, r, c.path, etch)
        end
    end
    if self.drag == 'stroke' and self.tool == 1 and #live > 1 then
        r:drawPath(polyPath(live, false), self.line)
    end
    -- the stencil job in progress
    local job = self.job
    if job ~= nil then
        local d = self.jobT * self.jobSpeed
        local part = {}
        local k, idx = along(job.pts, job.closed, d)
        for i = 1, math.min(idx - 1, #job.pts) do
            table.insert(part, job.pts[i])
        end
        table.insert(part, k)
        if job.kind == 'etch' then
            self.line.thickness = 22
            self.line.color = etch
        else
            self.line.thickness = if job.kind == 'etchfill' then 3 else 4
            self.line.color = if job.kind == 'etchfill' then etch else cut
        end
        if #part > 1 then
            r:drawPath(polyPath(part, false), self.line)
        end
    end
    self.line.thickness = 4.5
    self.line.color = cut
    for _, c in self.cuts do
        if c.kind == 'hole' then
            fill(self, r, c.path, cut)
            r:drawPath(c.path, self.line)
        elseif c.kind == 'slit' then
            r:drawPath(c.path, self.line)
        end
    end
    if self.drag == 'stroke' and self.tool ~= 1 and #live > 1 then
        r:drawPath(polyPath(live, false), self.line)
    end
    r:restore()
end

local function drawEmit(self: Scene, r: Renderer)
    local paint = self.paint
    local wx, wy, ww, wh = 70, 150, 190, 330
    -- night sky through the glass
    paint.gradient = Gradient.linear(Vector.xy(0, wy), Vector.xy(0, wy + wh), {
        { position = 0, color = rgb(30, 44, 78) },
        { position = 1, color = rgb(64, 70, 96) },
    })
    r:drawPath(rect(wx, wy, ww, wh), paint)
    paint.gradient = nil
    -- moon
    soft(self, r, wx + 120, wy + 92, 80, 80, { 130, 150, 210 }, 0.5)
    fill(self, r, ellipse(wx + 120, wy + 92, 26, 26), rgb(226, 230, 214))
    fill(self, r, ellipse(wx + 129, wy + 86, 22, 22), rgb(34, 46, 80))
    -- a bare branch across the glass
    self.line.color = rgb(8, 9, 14)
    self.line.thickness = 4
    local br = Path.new()
    br:moveTo(Vector.xy(wx, wy + 210))
    br:cubicTo(Vector.xy(wx + 50, wy + 190), Vector.xy(wx + 90, wy + 150), Vector.xy(wx + 150, wy + 140))
    br:moveTo(Vector.xy(wx + 70, wy + 178))
    br:cubicTo(Vector.xy(wx + 90, wy + 200), Vector.xy(wx + 120, wy + 210), Vector.xy(wx + 160, wy + 206))
    r:drawPath(br, self.line)
    -- stars
    for k = 1, 12 do
        local x = wx + 10 + hash(k * 9.1) * (ww - 20)
        local y = wy + 10 + hash(k * 4.7) * (wh * 0.6)
        local tw = 0.6 + 0.4 * math.sin(self.t * (1 + hash(k)) * 2 + k)
        fill(self, r, ellipse(x, y, 1.4, 1.4), Color.rgba(200, 210, 255, math.floor(160 * tw)))
    end
    -- mullions and frame
    fill(self, r, rect(wx + ww / 2 - 5, wy, 10, wh), rgb(0, 0, 0))
    fill(self, r, rect(wx, wy + wh * 0.42, ww, 10), rgb(0, 0, 0))
end

local function drawPuffs(self: Scene, r: Renderer)
    for _, p in self.puffs do
        if p.life > 0 then
            local a = math.sin(clamp01(p.life / p.max) * math.pi) * 0.55
            soft(self, r, p.x, p.y, p.r * 1.5, p.r * 1.2, { 170, 168, 176 }, a)
        end
    end
end

local function drawGhost(self: Scene, r: Renderer)
    if self.phantom <= 0.001 then
        return
    end
    -- two slanted eyes and a long smile, high on the wall, looking at you
    local cx = PX
    local cy = 166
    local look = clamp01((self.mouse.x - 200) / 900) * 2 - 1
    local lookY = clamp01((self.mouse.y - 100) / 600) * 2 - 1
    local b = self.blink % 4.3
    local open = if b < 0.16 then math.abs(b - 0.08) / 0.08 else 1
    for side = -1, 1, 2 do
        local ex = cx + side * 96
        local hh = 26 * open
        local e = { pt(ex - 62 * side, cy + 12) }
        bez(e, e[1], pt(ex - 30 * side, cy - hh - 6), pt(ex + 30 * side, cy - hh - 12), pt(ex + 58 * side, cy - 22), 10)
        bez(e, pt(ex + 58 * side, cy - 22), pt(ex + 30 * side, cy + hh * 0.6), pt(ex - 20 * side, cy + hh * 0.8 + 6), pt(ex - 62 * side, cy + 12), 10)
        fill(self, r, polyPath(cw(e), true), rgb(255, 255, 255))
        -- the pupil: a slit that follows the pointer
        if open > 0.4 then
            local px = ex + look * 22
            local py = cy - 6 + lookY * 6
            fill(self, r, ellipse(px, py, 5, 15 * open), rgb(0, 0, 0))
        end
    end
    local mo = { pt(cx - 160, cy + 60) }
    bez(mo, mo[1], pt(cx - 80, cy + 132), pt(cx + 80, cy + 132), pt(cx + 160, cy + 60), 16)
    bez(mo, pt(cx + 160, cy + 60), pt(cx + 80, cy + 110), pt(cx - 80, cy + 110), pt(cx - 160, cy + 60), 16)
    local m = polyPath(cw(mo), true)
    fill(self, r, m, rgb(255, 255, 255))
end

function draw(self: Scene, renderer: Renderer)
    local albedo = self.albedo
    local mask = self.mask
    local maskLo = self.maskLo
    local ghost = self.ghost
    local emit = self.emit
    local gpu = self.gpu
    local pipeline = self.pipeline
    local bind = self.bind
    local ubo = self.ubo
    if albedo == nil or mask == nil or maskLo == nil or ghost == nil or emit == nil or gpu == nil or pipeline == nil or bind == nil or ubo == nil then
        return
    end
    local s, ox, oy = fit(self)
    local q = self.q
    local xf = Mat2D.values(s * q, 0, 0, s * q, ox * q, oy * q)
    local xfLo = Mat2D.values(s * q / 4, 0, 0, s * q / 4, ox * q / 4, oy * q / 4)

    local ra = albedo:beginFrame()
    ra:save()
    ra:transform(xf)
    drawRoom(self, ra)
    drawPumpkin(self, ra)
    drawPuffs(self, ra)
    drawChunks(self, ra, false)
    drawKnife(self, ra, false)
    ra:restore()
    albedo:endFrame()

    local rm = mask:beginFrame({ clearColor = Color.rgba(0, 0, 0, 255) })
    rm:save()
    rm:transform(xf)
    drawCuts(self, rm)
    drawChunks(self, rm, true)
    drawKnife(self, rm, true)
    rm:restore()
    mask:endFrame()

    local rl = maskLo:beginFrame({ clearColor = Color.rgba(0, 0, 0, 255) })
    rl:save()
    rl:transform(xfLo)
    drawCuts(self, rl)
    drawChunks(self, rl, true)
    rl:restore()
    maskLo:endFrame()

    local rg = ghost:beginFrame({ clearColor = Color.rgba(0, 0, 0, 255) })
    rg:save()
    rg:transform(Mat2D.values(s * q / 2, 0, 0, s * q / 2, ox * q / 2, oy * q / 2))
    drawGhost(self, rg)
    rg:restore()
    ghost:endFrame()

    local re = emit:beginFrame({ clearColor = Color.rgba(0, 0, 0, 255) })
    re:save()
    re:transform(xf)
    drawEmit(self, re)
    re:restore()
    emit:endFrame()

    -- the candle sits low in the pumpkin; a gust or a hand bends it
    local flameX = PX + self.lean * 14
    local flameY = PY + 56
    local gustDip = 1 - 0.85 * math.sin(clamp01(self.gust) * math.pi * 0.5) ^ 2
    local flame = self.flameAmt * self.flicker * gustDip * (0.35 + 0.65 * self.flameSet / 100)

    local d = self.data
    local px = s * q
    buffer.writef32(d, 0, self.size.x * q)
    buffer.writef32(d, 4, self.size.y * q)
    buffer.writef32(d, 8, flameX * px + ox * q)
    buffer.writef32(d, 12, flameY * px + oy * q)
    buffer.writef32(d, 16, PX * px + ox * q)
    buffer.writef32(d, 20, (PY + 12) * px + oy * q)
    buffer.writef32(d, 24, RX * px)
    buffer.writef32(d, 28, RY * px)
    buffer.writef32(d, 32, self.t)
    buffer.writef32(d, 36, self.litAmt)
    buffer.writef32(d, 40, flame)
    buffer.writef32(d, 44, self.hazeSet / 100)
    buffer.writef32(d, 48, px)
    buffer.writef32(d, 52, self.lean)
    buffer.writef32(d, 56, self.phantom)
    buffer.writef32(d, 60, self.gust)
    buffer.writef32(d, 64, self.open)
    buffer.writef32(d, 68, self.flameAmt)
    buffer.writef32(d, 72, 0)
    buffer.writef32(d, 76, 0)
    ubo:write(d)

    local pass = gpu:beginRenderPass({ color = { { loadOp = 'clear', storeOp = 'store', clearColor = { 0, 0, 0, 1 } } } })
    pass:setPipeline(pipeline)
    pass:setBindGroup(0, bind)
    pass:draw(3)
    pass:finish()
    renderer:save()
    renderer:transform(Mat2D.values(1 / q, 0, 0, 1 / q, 0, 0))
    renderer:drawImage(gpu.image, ImageSampler('clamp', 'clamp', 'bilinear'), 'srcOver', 1)
    renderer:restore()
end

return function(context: Context): Layout<Scene>
    return {
        ctx = context,
        size = Vector.xy(0, 0),
        q = 1,
        t = 0,
        mouse = pt(-400, -400),
        mouseIn = false,
        speed = 0,
        lastMx = 0,
        lastMy = 0,
        lastMt = 0,
        drag = '',
        stroke = {},
        cuts = {},
        chunks = {},
        puffs = {},
        jobs = {},
        job = nil,
        jobT = 0,
        jobLen = 0,
        jobSpeed = 820,
        knife = pt(0, 0),
        knifeOn = 0,
        holes = 0,
        open = 0,
        jiggle = 0,
        jiggleV = 0,
        lit = false,
        litT = 10,
        litAmt = 0,
        flameAmt = 0,
        flicker = 1,
        lean = 0,
        leanV = 0,
        gust = 0,
        phantom = 0,
        phantomHold = 0,
        blink = 0,
        flameSet = 80,
        hazeSet = 60,
        tool = 0,
        story = 0,
        seed = 1,
        albedo = nil,
        mask = nil,
        maskLo = nil,
        ghost = nil,
        emit = nil,
        gpu = nil,
        pipeline = nil,
        ubo = nil,
        bind = nil,
        sampler = GPUSampler.new({ min = 'linear', mag = 'linear' }),
        data = buffer.create(112),
        paint = Paint.with({ color = Color.rgb(255, 255, 255) }),
        line = Paint.with({ style = 'stroke', thickness = 2, color = Color.rgb(0, 0, 0), cap = 'round', join = 'round' }),
        lobes = {},
        silhouette = Path.new(),
        face = Path.new(),
        grooves = {},
        stem = Path.new(),
        lid = Path.new(),
        vmTool = nil,
        vmLit = nil,
        vmStencil = nil,
        vmFresh = nil,
        vmFlame = nil,
        vmHaze = nil,
        vmEscape = nil,
        vmEscapeText = nil,
        vmFlameText = nil,
        vmHazeText = nil,
        vmCaption = nil,
        vmQuality = nil,
        caption = '',
        halo = { 1108, 189, 216, 42, 0, 0, 0, 0 },
        haloOn = 0,
        haloPress = 0,
        vmHalo = {},
        init = init,
        resize = resize,
        advance = advance,
        pointerDown = pointerDown,
        pointerMove = pointerMove,
        pointerUp = pointerUp,
        pointerExit = pointerExit,
        draw = draw,
    }
end
