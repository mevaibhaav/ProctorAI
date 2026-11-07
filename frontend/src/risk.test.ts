import { describe,expect,it } from 'vitest';
import { riskBand } from './risk';

describe('riskBand',()=>{
  it('uses the published score boundaries',()=>{
    expect([0,29,30,49,50,74,75,100].map(riskBand)).toEqual(['normal','normal','low','low','moderate','moderate','high','high']);
  });
});
