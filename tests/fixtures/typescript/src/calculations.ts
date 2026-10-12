// Intentional branching and duplication for analyzer acceptance.
export function complexDecision(value: number): number {
    let score = 0;
    if (value > 0) {
        score += 1;
    }
    if (value > 10) {
        score += 2;
    }
    if (value > 20) {
        score += 3;
    }
    if (value > 30) {
        score += 4;
    }
    if (value > 40) {
        score += 5;
    }
    if (value > 50) {
        score += 6;
    }
    if (value > 60) {
        score += 7;
    }
    if (value > 70) {
        score += 8;
    }
    if (value > 80) {
        score += 9;
    }
    if (value > 90) {
        score += 10;
    }
    if (value > 100) {
        score += 11;
    }
    if (value > 110) {
        score += 12;
    }
    return score;
}

export function normalizeValues(values: number[]): number[] {
    const result: number[] = [];
    for (const value of values) {
        if (value < 0) {
            result.push(0);
        } else {
            result.push(value);
        }
    }
    const total = result.reduce((sum, value) => sum + value, 0);
    return result.map((value) => total === 0 ? 0 : value / total);
}

export function normalizeValuesCopy(values: number[]): number[] {
    const result: number[] = [];
    for (const value of values) {
        if (value < 0) {
            result.push(0);
        } else {
            result.push(value);
        }
    }
    const total = result.reduce((sum, value) => sum + value, 0);
    return result.map((value) => total === 0 ? 0 : value / total);
}
