import { useEffect, useRef } from 'react'

const VERTEX_SHADER = `
  attribute vec2 a_position;
  void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
  }
`

const FRAGMENT_SHADER = `
  precision highp float;

  uniform vec2 u_resolution;
  uniform vec2 u_pointer;
  uniform float u_time;
  uniform float u_seed;
  uniform float u_family;
  uniform float u_motion;
  uniform vec3 u_accent;

  float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7)) + u_seed * 13.17) * 43758.5453);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
      mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
  }

  float line(float value, float width) {
    return 1.0 - smoothstep(0.0, width, abs(value));
  }

  void main() {
    vec2 frag = gl_FragCoord.xy;
    vec2 uv = (frag * 2.0 - u_resolution.xy) / min(u_resolution.x, u_resolution.y);
    vec2 pointer = (u_pointer * 2.0 - 1.0) * vec2(u_resolution.x / u_resolution.y, 1.0);
    float t = u_time * u_motion;
    float grain = hash(frag + floor(t * 24.0)) - 0.5;
    float vignette = 1.0 - smoothstep(0.2, 1.42, length(uv * vec2(0.78, 0.94)));
    float field = 0.0;
    float sparks = 0.0;

    if (u_family < 0.5) {
      float terrain = noise(uv * 2.6 + vec2(t * 0.035, -t * 0.022));
      field = line(fract(terrain * 8.0) - 0.5, 0.075) * 0.42;
      field += line(fract((uv.y + noise(uv * 1.4) * 0.22) * 9.0) - 0.5, 0.04) * 0.13;
    } else if (u_family < 1.5) {
      vec2 q = uv - pointer * 0.055;
      float radius = length(q);
      float angle = atan(q.y, q.x);
      field = line(fract(radius * 5.2 - t * 0.055) - 0.5, 0.038) * 0.42;
      field += line(sin(angle * (5.0 + mod(u_seed, 4.0)) + radius * 9.0 - t * 0.22), 0.08) * 0.18;
    } else if (u_family < 2.5) {
      float wave = sin(uv.x * 7.0 + t * 0.3 + noise(uv * 2.0) * 2.8) * 0.12;
      field = line(uv.y - wave, 0.018) * 0.52;
      field += line(fract((uv.y + t * 0.025) * 12.0) - 0.5, 0.025) * 0.1;
    } else if (u_family < 3.5) {
      vec2 grid = fract((uv + vec2(t * 0.012, 0.0)) * vec2(7.0, 4.0)) - 0.5;
      float blocks = step(0.39, max(abs(grid.x), abs(grid.y)));
      field = blocks * (0.08 + noise(floor(uv * vec2(7.0, 4.0))) * 0.16);
      field += line(sin((uv.x + uv.y) * 4.0 - t * 0.12), 0.055) * 0.1;
    } else if (u_family < 4.5) {
      vec2 cell = fract(uv * 4.2) - 0.5;
      vec2 id = floor(uv * 4.2);
      float node = 1.0 - smoothstep(0.025, 0.085, length(cell));
      float beam = line(cell.y - cell.x * (hash(id) - 0.5), 0.022);
      sparks = node * (0.45 + 0.55 * sin(t * 1.6 + hash(id) * 8.0));
      field = beam * 0.13 + sparks * 0.5;
    } else {
      vec2 q = abs(fract((uv + vec2(0.0, t * 0.008)) * vec2(3.0, 4.0)) - 0.5);
      field = line(max(q.x, q.y) - 0.43, 0.018) * 0.26;
      field += line(fract((uv.y + noise(uv * 2.2) * 0.08) * 14.0) - 0.5, 0.024) * 0.12;
    }

    float pointerGlow = 1.0 - smoothstep(0.0, 0.7, length(uv - pointer));
    vec3 base = vec3(0.012, 0.018, 0.014);
    vec3 color = base + u_accent * (field * vignette + pointerGlow * 0.035);
    color += vec3(grain * 0.012);
    gl_FragColor = vec4(color, clamp((field * 0.42 + pointerGlow * 0.025) * vignette + 0.24, 0.0, 0.58));
  }
`

const FAMILY_INDEX = {
  cartography: 0,
  observatory: 1,
  song: 2,
  lexicon: 3,
  graph: 4,
  archive: 5,
  atlas: 1,
  lost: 5,
}

function hexToRgb(hex) {
  const value = hex.replace('#', '')
  const full = value.length === 3 ? value.split('').map(char => char + char).join('') : value
  return [
    parseInt(full.slice(0, 2), 16) / 255,
    parseInt(full.slice(2, 4), 16) / 255,
    parseInt(full.slice(4, 6), 16) / 255,
  ]
}

function hashScene(value) {
  return [...value].reduce((sum, char) => ((sum << 5) - sum + char.charCodeAt(0)) | 0, 17)
}

function compile(gl, type, source) {
  const shader = gl.createShader(type)
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader) || 'Unable to compile cinematic shader')
  }
  return shader
}

export default function CinematicField({ scene, family }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const gl = canvas?.getContext('webgl', {
      alpha: true,
      antialias: false,
      depth: false,
      powerPreference: 'high-performance',
      premultipliedAlpha: true,
    })
    if (!canvas || !gl) {
      canvas?.setAttribute('data-webgl', 'unavailable')
      return undefined
    }

    let program
    try {
      program = gl.createProgram()
      gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX_SHADER))
      gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER))
      gl.linkProgram(program)
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program))
    } catch {
      canvas.setAttribute('data-webgl', 'unavailable')
      return undefined
    }

    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    gl.useProgram(program)

    const position = gl.getAttribLocation(program, 'a_position')
    gl.enableVertexAttribArray(position)
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0)

    const uniforms = {
      resolution: gl.getUniformLocation(program, 'u_resolution'),
      pointer: gl.getUniformLocation(program, 'u_pointer'),
      time: gl.getUniformLocation(program, 'u_time'),
      seed: gl.getUniformLocation(program, 'u_seed'),
      family: gl.getUniformLocation(program, 'u_family'),
      motion: gl.getUniformLocation(program, 'u_motion'),
      accent: gl.getUniformLocation(program, 'u_accent'),
    }

    const accent = hexToRgb(scene.accent)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const coarse = window.matchMedia('(pointer: coarse)').matches
    const pointer = { x: 0.5, y: 0.5 }
    let frame = 0
    let active = true
    let lastFrame = 0
    const started = performance.now()

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, coarse ? 1 : 1.35)
      const width = Math.max(1, Math.floor(canvas.clientWidth * ratio))
      const height = Math.max(1, Math.floor(canvas.clientHeight * ratio))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
        gl.viewport(0, 0, width, height)
      }
    }

    const render = now => {
      if (!active) return
      const frameInterval = coarse ? 1000 / 40 : 1000 / 60
      if (now - lastFrame >= frameInterval || reduced) {
        resize()
        lastFrame = now
        gl.uniform2f(uniforms.resolution, canvas.width, canvas.height)
        gl.uniform2f(uniforms.pointer, pointer.x, pointer.y)
        gl.uniform1f(uniforms.time, (now - started) / 1000)
        gl.uniform1f(uniforms.seed, Math.abs(hashScene(scene.key)) % 97)
        gl.uniform1f(uniforms.family, FAMILY_INDEX[family] ?? 1)
        gl.uniform1f(uniforms.motion, reduced ? 0 : 1)
        gl.uniform3fv(uniforms.accent, accent)
        gl.drawArrays(gl.TRIANGLES, 0, 3)
      }
      if (!reduced) frame = requestAnimationFrame(render)
    }

    const onPointer = event => {
      pointer.x = event.clientX / window.innerWidth
      pointer.y = 1 - event.clientY / window.innerHeight
    }
    const onVisibility = () => {
      const shouldRun = !document.hidden && window.scrollY < window.innerHeight * 1.35
      if (shouldRun === active) return
      active = shouldRun
      if (active && !reduced) frame = requestAnimationFrame(render)
      else cancelAnimationFrame(frame)
    }

    window.addEventListener('pointermove', onPointer, { passive: true })
    window.addEventListener('scroll', onVisibility, { passive: true })
    document.addEventListener('visibilitychange', onVisibility)
    resize()
    frame = requestAnimationFrame(render)

    return () => {
      active = false
      cancelAnimationFrame(frame)
      window.removeEventListener('pointermove', onPointer)
      window.removeEventListener('scroll', onVisibility)
      document.removeEventListener('visibilitychange', onVisibility)
      gl.deleteBuffer(buffer)
      gl.deleteProgram(program)
    }
  }, [scene.key, scene.accent, family])

  return <canvas ref={canvasRef} className="cinematic-field" aria-hidden="true" />
}
