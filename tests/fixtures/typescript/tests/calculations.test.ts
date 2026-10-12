import { complexDecision, normalizeValues } from "../src/calculations";

export function checkCalculations(): boolean {
    return complexDecision(0) === 0 && normalizeValues([-1, 2])[0] === 0;
}
