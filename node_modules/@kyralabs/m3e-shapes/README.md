# @kyralabs/m3e-shapes

TypeScript port of AndroidX graphics-shapes 1.0.1 (`RoundedPolygon`, `Morph`, …) and Compose
Material3's 35 `MaterialShapes`, float32-faithful to the JVM, with SVG path output.

```sh
npm install @kyralabs/m3e-shapes
```

## Usage

```ts
import { materialShape, polygonToPath, toSvgPathData } from '@kyralabs/m3e-shapes';

// Material shapes are normalized to a 0..1 box: <svg viewBox="0 0 1 1"><path d={d} /></svg>
const d = toSvgPathData(polygonToPath(materialShape('Cookie4Sided')));
```

`Morph` and `morphToPath` interpolate between two shapes; `materialShapeNames` lists the presets.

Apache-2.0; see `LICENSE` and `NOTICE`.
