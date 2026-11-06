function hasNewStream(previousGroups, currentGroups) {
    const known = new Set()
    for (const group of previousGroups) {
        for (const stream of group.streams)
            known.add(stream.index)
    }
    return currentGroups.some(group => group.streams.some(stream => !known.has(stream.index)))
}
