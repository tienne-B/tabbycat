<template>

  <td :class="cellData.class ? cellData.class : null" >

    <span v-if="cellData.sort" hidden>
      {{ cellData.checked }}
    </span>
    <div class="form-check">
      <input type="radio" class="form-check-input position-static"
             :name="cellData.name" :value="cellData.value"
             v-model.lazy="cellData.checked">
    </div>

  </td>

</template>

<script>
export default {
  mixins: [],
  props: {
    cellData: Object,
  },
  methods: {},
}

</script>
