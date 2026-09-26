// Registered via --import BEFORE the contract test loads, so the @/ alias
// resolve hooks apply to every subsequent import (including .ts sources
// handled by --experimental-strip-types).
import { register } from "node:module";

register("./alias-hooks.mjs", import.meta.url);
