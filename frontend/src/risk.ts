export function riskBand(score:number){if(score<30)return 'normal';if(score<50)return 'low';if(score<75)return 'moderate';return 'high'}
