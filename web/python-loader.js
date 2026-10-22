// Each Worker receives its own independent Python/WASM heap and virtual filesystem.
import {loadPyodide} from "/pyodide/pyodide.mjs";
import "/python-bootstrap.js";
export const python=(bundleURL,trusted=false)=>self.tankbotPython(bundleURL,trusted,loadPyodide);
