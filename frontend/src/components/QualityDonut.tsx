/**

 * Episode quality donut, 190px, as specified by the prototype.

 *

 * Accessibility: the ring is decorative and marked aria-hidden, because a

 * conic-gradient conveys nothing to a screen reader. The real content is the

 * legend beneath it, which gives each quality a text label, a count and a

 * percentage. Colour alone never carries the meaning.

 */



import { Badge } from './ui'

import type { Quality } from '../api/types'



export interface QualityCounts {

  good: number

  usable: number

  bad: number

}



// Matches the prototype's conic-gradient stops.

const SEGMENT_COLOURS: Record<Quality, string> = {

  good: '#4DCD87',

  usable: '#3B92F6',

  bad: '#F46676',

}



const ORDER: Quality[] = ['good', 'usable', 'bad']



export function QualityDonut({ counts }: { counts: QualityCounts }) {

  const total = counts.good + counts.usable + counts.bad



  // Cumulative stops, so the three arcs meet exactly rather than leaving a

  // seam from rounding each slice independently.

  const goodEnd = total > 0 ? (counts.good / total) * 100 : 0

  const usableEnd = total > 0 ? ((counts.good + counts.usable) / total) * 100 : 0



  const gradient =

    total > 0

      ? `conic-gradient(${SEGMENT_COLOURS.good} 0 ${String(goodEnd)}%, ` +

        `${SEGMENT_COLOURS.usable} 0 ${String(usableEnd)}%, ` +

        `${SEGMENT_COLOURS.bad} 0 100%)`

      : // Nothing imported yet: a flat ring rather than a misleading full slice.

        '#f0f2f6'



  const share = (value: number) =>

    total > 0 ? `${((value / total) * 100).toFixed(0)}%` : '0%'



  return (

    <>

      <div className="quality-donut-layout">
        <div className="donut" style={{ background: gradient }} aria-hidden="true">
          <span>
            <strong>{total}</strong>
            <small>total</small>
          </span>
        </div>

        <ul className="donut-legend">

          {ORDER.map((quality) => (

            <li className="row between" key={quality}>

              <Badge kind={quality} />

              <span>

                <strong>{counts[quality]}</strong>{' '}

                <small className="muted">{share(counts[quality])}</small>

              </span>

            </li>

          ))}

        </ul>
      </div>

      {total === 0 ? (

        <p className="help">No episodes imported yet.</p>

      ) : (

        <p className="help">

          {total} episode{total === 1 ? '' : 's'} in the inventory. Only good and

          usable episodes can be assigned.

        </p>

      )}

    </>

  )

}

